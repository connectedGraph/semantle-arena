"""Agent 运行期：只通过工具访问对局状态。

设计边界（与论文里的分层一致）
------------------------------
- Agent **看不到答案**。它只有两个工具：
  - `guess(words)`  批量猜词，拿回相似度与名次
  - `review(k)`     整理自己猜过的词，不产生新信息
- 胜负按「猜中时用掉的不同词数」比，不按回合、不按耗时。
- 单轮可并行多个 tool_call，后端用 asyncio.gather 并发执行。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx

from ..models import Game, Guess
from ..store import Store

logger = logging.getLogger(__name__)

MAX_BATCH = 64

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "guess",
            "description": (
                "提交一组猜测词。返回每个词与隐藏答案的语义相似度百分比和名次"
                "（rank 越小越接近，rank=1 是最接近答案的词）。"
                "**每个新词都计入你的成绩**（重复的不算），所以只交有信息量的词。"
                "猜中时相似度为 100。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "words": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": f"要猜的中文词，最多 {MAX_BATCH} 个",
                    }
                },
                "required": ["words"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "review",
            "description": (
                "把你自己已经猜过的词按接近程度重新排一遍"
                "（相似度降序 / 名次升序，一行一词）。"
                "k=-1 表示全部。只做回顾，不产生新猜测，不透露答案。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "k": {
                        "type": "integer",
                        "description": "只看最接近的前 k 条；-1 为全部",
                        "default": -1,
                    }
                },
                "required": [],
            },
        },
    },
]

SYSTEM_PROMPT = """你在参加一场中文语义猜词比赛（Semantle）。

规则：
- 有一个隐藏的中文目标词，字数已知。你只能用下面两个工具获取信息。
- guess(words)：一次可并行提交多个词，返回每个词的相似度百分比和名次。
  rank=1 表示这是目前最接近答案的词；词就是答案本身时相似度为 100.00%。
- review(k)：把你猜过的词按接近程度整理返回，不产生新猜测。

目标：用尽量少的**词数**猜中答案。胜负只看你猜中时一共交了多少个不同的词，
和对手比，少者胜；用了几轮、花了多久都不算。一次交 20 个词就是 20 个词的代价。

策略：
- **猜测词要和答案字数一致**。答案是 2 个字就猜 2 字词，猜 1 个字会得到系统性偏低的分数
  （单字和双字在向量空间里距离本来就远），那种低分不代表方向错，别被它误导。
- 开局交一小组（6~8 个）语义上互不相干的常见名词，判断答案落在哪个领域；
- 之后每轮只交 2~5 个你认为最有可能的词，宁可多想一轮也别撒网；
- 拿到结果后，沿最接近的几个方向发散，而不是盯着一个词找近义词；
- 相似度衡量的是「语义相关」，不是「同义」。最接近的词常常是同类事物而不是近义词；
- 如果连续 2~3 轮最高相似度都在同一区间打转，说明方向错了，主动换一个完全不同的语义维度；
- **优先看名次（rank），不要只看相似度百分比**。短词的余弦分普遍偏高且彼此接近，
  60%~70% 这一段基本没有区分度；而 rank 是在整个词池里排出来的相对位置，信号强得多。
  rank 300 以内才算摸到边，rank 50 以内才算接近。
- 留意分数的**绝对高低**：如果最高的词也只有 60% 出头，说明还没摸到边；
- 不要空谈，用工具拿数据决策。"""


def _system_message(target_len: int) -> Dict[str, str]:
    return {
        "role": "system",
        "content": f"{SYSTEM_PROMPT}\n\n本局答案字数：{target_len} 个字。",
    }


class ToolExecutor:
    """把工具调用绑定到某一局 Agent 侧的游戏上。"""

    def __init__(self, store: Store, game: Game, step: int = 1) -> None:
        self.store = store
        self.game = game
        self.step = step

    def guess(self, words: List[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        seen: set[str] = set()
        guessed = {g.word: g for g in self.game.history}
        for raw in (words or [])[:MAX_BATCH]:
            w = (raw or "").strip()
            if not w or w in seen:
                continue
            seen.add(w)
            if w in guessed:  # 猜过就复用，不计入新次数
                g = guessed[w]
                rows.append(self._row(g, reused=True))
                continue
            g = self.store.score(self.game, w, source="agent", step=self.step)
            rows.append(self._row(g))
        return rows

    @staticmethod
    def _row(g: Guess, reused: bool = False) -> Dict[str, Any]:
        return {
            "word": g.word,
            "similarity_pct": g.similarity_pct,
            "rank": g.rank if g.rank is not None else None,
            "level": g.level,
            "is_target": g.is_target,
            "reused": reused,
        }

    def review(self, k: int = -1) -> List[Dict[str, Any]]:
        rows = sorted(self.game.history,
                      key=lambda g: (g.rank is None, g.rank or 10**9, -g.similarity))
        if k is not None and k > 0:
            rows = rows[:k]
        return [self._row(g) for g in rows]

    def execute(self, name: str, args: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        if name == "guess":
            rows = self.guess(args.get("words") or [])
        elif name == "review":
            rows = self.review(int(args.get("k", -1)))
        else:
            return f"未知工具：{name}", []
        return format_rows(rows), rows


def format_rows(rows: List[Dict[str, Any]]) -> str:
    """紧凑格式，省 token：rank / word / similarity。"""
    lines = ["rank\tword\tsimilarity_pct"]
    for r in rows:
        rank = r["rank"] if r["rank"] is not None else "3000+"
        mark = "  ← 命中" if r.get("is_target") else ("  (已猜过)" if r.get("reused") else "")
        lines.append(f"{rank}\t{r['word']}\t{r['similarity_pct']:.2f}{mark}")
    return "\n".join(lines)


def _gateway_key() -> str:
    """从 ~/llm.yaml 读本机网关的 key，避免在项目里再抄一份。

    只做最简单的行解析（key: xxx），不引入 yaml 依赖；解析失败就返回空串，
    由环境变量兜底。
    """
    path = os.path.expanduser("~/llm.yaml")
    try:
        for line in open(path, encoding="utf-8"):
            s = line.strip()
            if s.startswith("api_key:"):
                return s.split(":", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


class LLMClient:
    """OpenAI 兼容的 chat/completions 客户端。默认走本机网关，也可填 DeepSeek 官方。"""

    def __init__(self) -> None:
        self.base_url = (os.environ.get("ARENA_LLM_BASE_URL")
                         or "http://127.0.0.1:8787/v1").rstrip("/")
        self._local = "127.0.0.1" in self.base_url or "localhost" in self.base_url
        # 本机网关的 key 只在 ~/llm.yaml 里有一份；远程服务必须显式配环境变量
        self.api_key = (os.environ.get("ARENA_LLM_API_KEY")
                        or (_gateway_key() if self._local else ""))
        if not self.api_key:
            logger.warning("没有可用的 ARENA_LLM_API_KEY，Agent 调用会失败")
        self.model = os.environ.get("ARENA_LLM_MODEL", "workbuddy/deepseek-v4.1-flash")
        self.proxy = os.environ.get("ARENA_LLM_PROXY", "").strip() or None
        self.temperature = float(os.environ.get("ARENA_LLM_TEMPERATURE", "0.7"))

    async def chat(self, messages: List[Dict[str, Any]],
                   tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": self.temperature,
        }
        async with httpx.AsyncClient(
            timeout=90.0, proxy=self.proxy, trust_env=not self._local
        ) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            return resp.json()


EmitFn = Callable[[Dict[str, Any]], Awaitable[None]]


class AgentRunner:
    """Agent 主循环：模型 -> 并行执行工具 -> 回填 -> 直到命中或步数用尽。"""

    def __init__(self, store: Store, client: LLMClient, game: Game,
                 emit: EmitFn, max_steps: int = 30,
                 should_stop: Optional[Callable[[], bool]] = None) -> None:
        self.store = store
        self.client = client
        self.game = game
        self.emit = emit
        self.max_steps = max_steps
        self.should_stop = should_stop or (lambda: False)
        self.executor = ToolExecutor(store, game)
        self.steps = 0

    async def _run_tool(self, call: Dict[str, Any]) -> Dict[str, Any]:
        fn = call.get("function") or {}
        name = fn.get("name") or ""
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        await self.emit({"type": "tool_call", "id": call.get("id"),
                         "name": name, "args": args})
        try:
            text, rows = self.executor.execute(name, args)
        except Exception as exc:  # noqa: BLE001
            logger.exception("工具执行失败")
            text, rows = f"工具执行失败：{exc}", []
        await self.emit({"type": "tool_result", "id": call.get("id"),
                         "name": name, "text": text, "rows": rows})
        return {"role": "tool", "tool_call_id": call.get("id"), "content": text}

    async def run(self) -> Dict[str, Any]:
        messages: List[Dict[str, Any]] = [
            _system_message(len(self.game.target)),
            {"role": "user", "content": "开始。先提交第一组试探词。"},
        ]
        solved = False

        for step in range(self.max_steps):
            if self.should_stop() or self.game.finished:
                break
            self.steps = step + 1
            self.executor.step = self.steps
            await self.emit({"type": "step", "step": self.steps,
                             "max_steps": self.max_steps})

            try:
                resp = await self.client.chat(messages, TOOL_SCHEMAS)
            except Exception as exc:  # noqa: BLE001
                await self.emit({"type": "error", "message": f"模型调用失败：{exc}"})
                break

            msg = (resp.get("choices") or [{}])[0].get("message") or {}
            content = (msg.get("content") or "").strip()
            tool_calls = msg.get("tool_calls") or []

            if content:
                await self.emit({"type": "assistant", "step": self.steps, "text": content})

            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": tool_calls or None,
            })

            if not tool_calls:
                if self.game.finished:
                    break
                # 模型只想说话不动手：催一次
                messages.append({"role": "user", "content": "请用工具继续猜，别只说话。"})
                continue

            results = await asyncio.gather(*(self._run_tool(c) for c in tool_calls))
            messages.extend(results)

            if self.game.finished:
                solved = True
                await self.emit({"type": "solved", "step": self.steps,
                                 "guesses": self.game.guess_count})
                break

        await self.emit({"type": "agent_done", "solved": solved or self.game.finished,
                         "steps": self.steps, "guesses": self.game.guess_count})
        return {"solved": solved or self.game.finished,
                "steps": self.steps, "guesses": self.game.guess_count}
