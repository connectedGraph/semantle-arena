"""HTTP 层：对局 API 与 SSE 事件流。

事件类型（SSE）
---------------
snapshot  start  step  assistant  tool_call  tool_result
human_guess  human_done  solved  agent_done  race_end  error

防泄露
------
- 对局进行中，`snapshot` 不带 target；
- 人类猜词的响应只回自己的记录；
- 答案只在 `race_end` 里出现。
"""
from __future__ import annotations

import asyncio
import json
import queue
import logging
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from .agent.runner import AgentRunner, LLMClient
from .models import Game, Race
from .store import get_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

MAX_GUESS_LEN = 8


def _valid_word(w: str) -> bool:
    return 1 <= len(w) <= MAX_GUESS_LEN and all("一" <= c <= "鿿" for c in w)


class GuessIn(BaseModel):
    word: str = Field(..., min_length=1, max_length=32)

    @field_validator("word")
    @classmethod
    def _v(cls, v: str) -> str:
        v = v.strip()
        if not _valid_word(v):
            raise ValueError(f"只能输入 1~{MAX_GUESS_LEN} 个汉字")
        return v


class RaceIn(BaseModel):
    mode: str = "versus"
    target_word: Optional[str] = None
    min_len: int = 2
    max_len: int = 4
    max_steps: int = 30

    @field_validator("mode")
    @classmethod
    def _m(cls, v: str) -> str:
        if v not in ("versus", "challenge"):
            raise ValueError("mode 只能是 versus 或 challenge")
        return v

    @field_validator("max_steps")
    @classmethod
    def _s(cls, v: int) -> int:
        if not 1 <= v <= 50:
            raise ValueError("max_steps 需在 1~50 之间")
        return v

    @field_validator("target_word")
    @classmethod
    def _t(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not _valid_word(v):
            raise ValueError(f"出题只能输入 1~{MAX_GUESS_LEN} 个汉字")
        return v


def _get_race(race_id: str) -> Race:
    race = get_store().races.get(race_id)
    if race is None:
        raise HTTPException(404, "对局不存在")
    return race


@router.get("/meta")
def meta() -> Dict[str, Any]:
    """前端启动时读一次：词池规模、引擎参数、可用模型。"""
    engine = get_store().engine
    return {
        "pool": engine.meta,
        "config": engine.config,
        "models": {
            "embedding": engine.meta["engine"],
            "agent": LLMClient().model,
        },
        # 当前档位 + 可选档位，前端据此渲染切换器
        "tier": engine.tier,
        "tiers": engine.available_tiers(),
    }


class TierIn(BaseModel):
    tier: str = Field(..., min_length=1)

    @field_validator("tier")
    @classmethod
    def _v(cls, v: str) -> str:
        if v not in ("small", "medium", "full"):
            raise ValueError("tier 只能是 small / medium / full")
        return v


@router.post("/tier")
def set_tier(body: TierIn) -> Dict[str, Any]:
    """切换词库档位。

    注意：档位是**全局**的（单进程内存引擎），切了会影响正在进行的所有对局。
    这是有意的简化——多用户场景下应该按对局隔离，见 README 的已知限制。
    """
    store = get_store()
    try:
        store.engine.set_tier(body.tier)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"tier": store.engine.tier, "count": store.engine.size,
            "tiers": store.engine.available_tiers()}


@router.get("/pool/sample")
def pool_sample(n: int = 12, length: Optional[int] = None) -> Dict[str, Any]:
    """抽样看词池，供 UI 展示「词表覆盖」。"""
    engine = get_store().engine
    words = [w for w in engine.words if length is None or len(w) == length]
    step = max(1, len(words) // max(1, n))
    return {"count": len(words), "sample": words[::step][:n]}


@router.post("/race")
def create_race(req: RaceIn) -> Dict[str, Any]:
    race = get_store().create_race(req.mode, req.target_word,
                                   req.min_len, req.max_len, req.max_steps)
    return _snapshot(race)


def _snapshot(race: Race) -> Dict[str, Any]:
    return {
        "race_id": race.race_id,
        "mode": race.mode,
        "max_steps": race.max_steps,
        "target_length": len(race.target),
        "target": race.target if race.finished else None,
        "started": race.started,
        "finished": race.finished,
        "winner": race.winner,
        "human_done": race.human_done,
        "agent_done": race.agent_done,
        "human_solved": race.human_game.finished,
        "agent_solved": race.agent_game.finished,
        "human_guesses": race.human_game.guess_count,
        "agent_guesses": race.agent_game.guess_count,
        # 胜负口径：猜中时用掉的词数（少者胜）
        "human_words": race.human_game.until_solved_guesses(),
        "agent_words": race.agent_game.until_solved_guesses(),
        "human_history": [g.to_dict() for g in race.human_game.history],
        "agent_history": [g.to_dict() for g in race.agent_game.history],
    }


@router.get("/race/{race_id}")
def get_race(race_id: str) -> Dict[str, Any]:
    return _snapshot(_get_race(race_id))


@router.post("/race/{race_id}/guess")
def human_guess(race_id: str, body: GuessIn) -> Dict[str, Any]:
    race = _get_race(race_id)
    if race.human_done:
        raise HTTPException(400, "本局你已经结束了")
    store = get_store()
    g = store.score(race.human_game, body.word, source="human")
    if race.human_game.finished:
        race.human_done = True
    _settle(race)
    return {"guess": g.to_dict(), "human_done": race.human_done,
            "human_guesses": race.human_game.guess_count}


@router.post("/race/{race_id}/giveup")
def human_giveup(race_id: str) -> Dict[str, Any]:
    race = _get_race(race_id)
    race.human_done = True
    _settle(race)
    return {"human_done": True, "finished": race.finished, "winner": race.winner}


@router.post("/race/{race_id}/abort")
def abort_race(race_id: str) -> Dict[str, Any]:
    """放弃这一局（前端换设置/关页面时调）。

    只让 Agent 循环退出，不写结算——这一局本就不该有结果。
    存在的意义是别让没人看的对局在后台继续烧 token。
    """
    race = _get_race(race_id)
    race.aborted = True
    return {"ok": True}


def _settle(race: Race) -> None:
    """结算；若已结束，向事件队列投一条 race_end。

    这里**必须是同步投递**：`human_guess` / `human_giveup` 是同步端点，
    FastAPI 会把它们跑在线程池里，此时没有事件循环，`asyncio.create_task`
    会抛 `RuntimeError: no running event loop`，反过来把请求打挂。
    `asyncio.Queue.put_nowait` 在没有循环时也能用（队列本身就是线程安全的 put 目标，
    消费端在自己的循环里 await）。
    """
    prev = race.finished
    winner = race.settle()
    if race.finished and not prev:
        race.emit_nowait({
            "type": "race_end",
            "race_id": race.race_id,
            "target": race.target,
            "winner": winner,
            "human_guesses": race.human_game.guess_count,
            "agent_guesses": race.agent_game.guess_count,
            "human_words": race.human_game.until_solved_guesses(),
            "agent_words": race.agent_game.until_solved_guesses(),
            "human_solved": race.human_game.finished,
            "agent_solved": race.agent_game.finished,
        })


@router.post("/race/{race_id}/start")
async def start_agent(race_id: str) -> Dict[str, Any]:
    race = _get_race(race_id)
    if race.started:
        return {"ok": True, "already": True}
    race.started = True
    asyncio.create_task(_run_agent(race))
    return {"ok": True}


async def _run_agent(race: Race) -> None:
    async def emit(event: Dict[str, Any]) -> None:
        event.setdefault("race_id", race.race_id)
        await race.emit(event)

    await emit({"type": "start", "max_steps": race.max_steps})
    runner = AgentRunner(get_store(), LLMClient(), race.agent_game, emit,
                         max_steps=race.max_steps,
                         should_stop=lambda: race.aborted
                         or (race.human_game.finished and race.human_done))
    try:
        result = await runner.run()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Agent 运行异常")
        await emit({"type": "error", "message": str(exc)})
        result = {"solved": False}
    race.agent_done = True
    _settle(race)


@router.get("/race/{race_id}/events")
async def events(race_id: str) -> Any:
    from fastapi.responses import StreamingResponse

    race = _get_race(race_id)

    async def gen() -> AsyncGenerator[str, None]:
        yield _sse({"type": "snapshot", **_snapshot(race)})
        while True:
            # queue.Queue.get 是阻塞的，丢到线程里取，避免堵住事件循环
            try:
                event = await asyncio.wait_for(
                    asyncio.to_thread(race.events.get, True, 15.0), timeout=20.0
                )
            except (asyncio.TimeoutError, queue.Empty):
                yield ": keepalive\n\n"
                # 对局已结束且队列空了，没必要继续挂着
                if race.finished:
                    break
                continue
            yield _sse(event)
            if event.get("type") == "race_end":
                break

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
