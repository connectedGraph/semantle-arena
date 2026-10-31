"""对局数据模型。

分开三件事（不要混）
--------------------
- Game      : 一局游戏的状态与历史，与谁在猜无关
- Race      : 人类与 Agent 猜同一个谜底的对抗容器
- TurnEvent : 推给前端的事件（思考 / 工具调用 / 结果）

胜负口径：猜中答案所用的**猜测次数**少者胜。LLM 回得快是速度优势，不参与比较。
"""
from __future__ import annotations

import queue
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

ProximityLevel = Literal["hot", "warm", "cold", "exact"]

# 排名分档：hot / warm 用于前端配色与提示
HOT_RANK = 300
WARM_RANK = 3000


@dataclass
class Guess:
    order: int
    word: str
    similarity: float          # 原始余弦相似度（-1~1）
    rank: Optional[int]        # 按排序分算出的名次，1 = 最接近
    level: ProximityLevel
    is_target: bool
    source: Literal["human", "agent"] = "human"
    at: float = field(default_factory=time.time)
    # 池外词用汉字向量平均近似，分数只作参考——界面要标出来，
    # 否则玩家会以为「干饭搭子只有 37%」意味着不接近，其实是估算
    approx: bool = False
    # 归一化后的显示百分比（相对于本局最接近的那个词）。
    # 腾讯词向量的原始余弦普遍偏低，直接显示会误导；排序仍用原始分。
    shown_pct: Optional[float] = None
    # Agent 侧：这是第几个对话回合产生的猜测（人类侧为 None）。
    # 一次 guess 可以包含多个词，但只消耗回合预算，不按词数计。
    step: Optional[int] = None

    @property
    def similarity_pct(self) -> float:
        """展示用百分比：归一化到本局最接近的词 = 99%。"""
        if self.shown_pct is not None:
            return self.shown_pct
        return round(self.similarity * 100, 2)

    @property
    def raw_pct(self) -> float:
        """原始余弦百分比，用于排查。"""
        return round(self.similarity * 100, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order": self.order,
            "word": self.word,
            "similarity": round(self.similarity, 6),
            "similarity_pct": self.similarity_pct,
            "raw_pct": self.raw_pct,
            "rank": self.rank,
            "level": self.level,
            "is_target": self.is_target,
            "source": self.source,
            "at": self.at,
            "step": self.step,
            "approx": self.approx,
        }


def level_of(rank: Optional[int], is_target: bool) -> ProximityLevel:
    if is_target:
        return "exact"
    if rank is None:
        return "cold"
    if rank <= HOT_RANK:
        return "hot"
    if rank <= WARM_RANK:
        return "warm"
    return "cold"


@dataclass
class Game:
    """一局猜词的完整状态。"""

    target: str
    game_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    history: List[Guess] = field(default_factory=list)
    # 目标词的邻居缓存（首次猜词时算一次）
    _ranks: Dict[str, int] = field(default_factory=dict)
    _rank_scores: List[float] = field(default_factory=list)
    _rank_ready: bool = False
    finished: bool = False

    @property
    def guess_count(self) -> int:
        """猜过的不同词数（含重复提交的旧结果去重前的原始条数）。"""
        return len(self.history)

    @property
    def turn_count(self) -> int:
        """消耗的回合数。

        Agent 一侧一次工具调用可以提交几十个词，但那只算一个回合——
        回合才是「思考代价」，词数不是。人类的每次提交都是独立回合。
        """
        steps = {g.step for g in self.history if g.step is not None}
        human_like = sum(1 for g in self.history if g.step is None)
        return len(steps) + human_like

    def until_solved_turns(self) -> int:
        """猜中那一刻为止消耗的回合数。

        猜中之后的猜测不计入胜负判定——否则先猜中的人反而可能因为
        后续继续猜测而「输」。
        """
        turns = 0
        counted: set = set()
        for g in self.history:
            if g.step is None:
                turns += 1
            elif g.step not in counted:
                counted.add(g.step)
                turns += 1
            if g.is_target:
                break
        return turns

    def add(self, guess: Guess) -> None:
        self.history.append(guess)
        if guess.is_target:
            self.finished = True

    def snapshot(self) -> Dict[str, Any]:
        return {
            "game_id": self.game_id,
            "target_length": len(self.target),
            "finished": self.finished,
            "guess_count": self.guess_count,
            "history": [g.to_dict() for g in self.history],
        }


@dataclass
class Race:
    """人类 vs Agent 的对局。"""

    human_game: Game
    agent_game: Game
    mode: Literal["versus", "challenge"] = "versus"
    max_steps: int = 30
    race_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    started: bool = False
    finished: bool = False
    winner: Optional[Literal["human", "agent", "tie"]] = None
    agent_done: bool = False
    human_done: bool = False
    # SSE 事件队列。
    # 用标准库 queue.Queue 而不是 asyncio.Queue：投递方可能是 FastAPI 的线程池
    # （同步端点），也可能是事件循环里的协程，跨线程 put 只有 queue.Queue 安全。
    # 消费端在自己的循环里用 asyncio.to_thread 取。
    events: "queue.Queue" = field(default_factory=lambda: queue.Queue(maxsize=1000), repr=False)

    @property
    def target(self) -> str:
        return self.human_game.target

    async def emit(self, event: Dict[str, Any]) -> None:
        """协程侧投递。满了就丢最旧的，避免慢客户端把内存吃光。"""
        event.setdefault("race_id", self.race_id)
        self.emit_nowait(event)

    def emit_nowait(self, event: Dict[str, Any]) -> None:
        """任何线程都能调。"""
        event.setdefault("race_id", self.race_id)
        try:
            self.events.put_nowait(event)
        except queue.Full:
            try:
                self.events.get_nowait()
                self.events.put_nowait(event)
            except queue.Empty:
                pass

    def settle(self) -> Optional[str]:
        """结算。只有双方都结束时才有结果。"""
        if self.finished:
            return self.winner
        if self.mode == "versus" and not (self.agent_done and self.human_done):
            return None
        if self.mode == "challenge" and not self.agent_done:
            return None

        agent_solved = self.agent_game.finished
        human_solved = self.human_game.finished

        if self.mode == "challenge":
            self.winner = "agent" if agent_solved else "tie"
        elif agent_solved and human_solved:
            # 比回合数：Agent 一次 submit 多词仍算一回合，人类每次算一回合
            ah = self.agent_game.until_solved_turns()
            hh = self.human_game.until_solved_turns()
            self.winner = "agent" if ah < hh else "human" if hh < ah else "tie"
        elif agent_solved:
            self.winner = "agent"
        elif human_solved:
            self.winner = "human"
        else:
            self.winner = "tie"

        self.finished = True
        return self.winner
