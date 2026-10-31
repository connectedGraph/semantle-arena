"""对局数据模型。

分开三件事（不要混）
--------------------
- Game      : 一局游戏的状态与历史，与谁在猜无关
- Race      : 人类与 Agent 猜同一个谜底的对抗容器
- TurnEvent : 推给前端的事件（思考 / 工具调用 / 结果）

胜负口径：猜中答案所**用掉的词数**少者胜。
不按耗时比——模型回得快是速度优势，不是游戏能力；
也不按轮次比——那样 Agent 一次丢 64 个词就算「一轮」，人类一次只能一个，没法公平。
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

    def until_solved_guesses(self) -> int:
        """猜中那一刻为止用掉的词数。

        胜负就按这个数比：少者胜。人类每次提交一个词，Agent 一次可以交
        一批——所以 Agent 的真实成本天然更高，这是有意的（它靠并行搜索换词数，
        不是靠聪明）。
        猜中之后的词不计入——否则先猜中的人反而可能因为继续试探而「输」。
        """
        n = 0
        for g in self.history:
            n += 1
            if g.is_target:
                break
        return n

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
    # 前端开了新一局（切档位/换模式）时置位：旧局的 Agent 循环看到就退出，
    # 免得后台还在为没人看的一局烧 token。
    aborted: bool = False
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

    def human_cannot_win(self) -> bool:
        """Agent 已命中，且人类已用掉不少于 Agent 的词数还没命中 → 胜负已定。

        按词数比的直接推论：Agent 用 N 个词命中，人类第 N 个词命中是平局，
        用完 N 个词还没命中就既赢不了也平不了，没必要让玩家猜到天荒地老才结算。
        所以判据是「已用词数 >= N 且未命中」。
        """
        if self.mode != "versus" or not self.agent_game.finished:
            return False
        if self.human_game.finished:
            return False
        return self.human_game.guess_count >= self.agent_game.until_solved_guesses()

    def settle(self) -> Optional[str]:
        """结算。只有双方都结束时才有结果。"""
        if self.finished:
            return self.winner
        if self.human_cannot_win():
            self.human_done = True
        if self.mode == "versus" and not (self.agent_done and self.human_done):
            return None
        if self.mode == "challenge" and not self.agent_done:
            return None

        agent_solved = self.agent_game.finished
        human_solved = self.human_game.finished

        if self.mode == "challenge":
            self.winner = "agent" if agent_solved else "tie"
        elif agent_solved and human_solved:
            # 比词数：谁猜中时用掉的词少谁赢
            ah = self.agent_game.until_solved_guesses()
            hh = self.human_game.until_solved_guesses()
            self.winner = "agent" if ah < hh else "human" if hh < ah else "tie"
        elif agent_solved:
            self.winner = "agent"
        elif human_solved:
            self.winner = "human"
        else:
            self.winner = "tie"

        self.finished = True
        return self.winner
