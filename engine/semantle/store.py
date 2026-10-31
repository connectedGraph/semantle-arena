"""会话存储：把引擎计算包成对局操作。

性能约定
--------
每局游戏只在**首次猜词**时建立一次完整名次表（`_ranks`），之后每次猜词是
字典查表 O(1)。池外词用一次二分插入得到近似名次，不重建整表。

排名口径
--------
名次按「排序分」（语义相似度 - 字符重叠惩罚）算，与邻居表同一口径，
所以游戏过程中显示的名次和谜底自己的邻居顺序一致。
"""
from __future__ import annotations

import bisect
import random
import threading
from typing import Dict, List, Optional

from fastapi import HTTPException

from .embedder import Engine, get_engine
from .models import Game, Guess, Race, level_of

# 名次表只保留前这么多，超出显示 "3000+"
RANK_CAP = 3000


class Store:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.races: Dict[str, Race] = {}
        self._lock = threading.Lock()

    # ---------- 排名 ----------

    def _prime(self, game: Game) -> None:
        """建立本局的完整名次表。只在首次猜词时执行一次。

        名次口径：谜底自己**不占名次**。rank 1 是「除答案外最接近的词」。
        否则所有猜词的名次都会整体后移一位，且 rank=1 永远只属于答案本身，
        玩家看到「最近才 rank 2」会误以为还没接近。
        """
        nb = self.engine.neighbors(game.target, k=min(RANK_CAP + 1, self.engine.size))
        nb = [(w, raw, adj) for (w, raw, adj) in nb if w != game.target][:RANK_CAP]
        game._ranks = {w: i + 1 for i, (w, _, _) in enumerate(nb)}
        game._rank_scores = [s for _, _, s in nb]   # 降序，供二分
        game._rank_ready = True

    def _rank_for(self, game: Game, word: str, adj: float) -> Optional[int]:
        if word in game._ranks:
            return game._ranks[word]
        # 池外词：排序分在本局邻居表中的插入位置
        scores: List[float] = game._rank_scores  # type: ignore[attr-defined]
        pos = bisect.bisect_right([-s for s in scores], -adj)
        return pos + 1 if pos < RANK_CAP else None

    # ---------- 猜词 ----------

    def score(self, game: Game, word: str, source: str = "human",
              step: Optional[int] = None) -> Guess:
        engine = self.engine
        if not game._rank_ready:
            self._prime(game)

        target_vec = engine.vector(game.target)
        raw = engine.raw_similarity(target_vec, word)
        adj = engine.adjusted(game.target, word, raw)
        is_target = word == game.target
        rank = 1 if is_target else self._rank_for(game, word, adj)

        g = Guess(
            order=game.guess_count + 1,
            word=word,
            similarity=raw,
            rank=rank,
            level=level_of(rank, is_target),
            is_target=is_target,
            source=source,  # type: ignore[arg-type]
            step=step,
        )
        with self._lock:
            game.add(g)
        return g

    # ---------- 建局 ----------

    def pick_target(self, min_len: int, max_len: int,
                    exclude: Optional[str] = None) -> str:
        candidates = [w for w in self.engine.words
                      if min_len <= len(w) <= max_len and w != exclude]
        if not candidates:
            raise HTTPException(400, f"没有 {min_len}~{max_len} 字的可用谜底")
        return random.choice(candidates)

    def create_race(self, mode: str, target: Optional[str], min_len: int,
                    max_len: int, max_steps: int) -> Race:
        word = target or self.pick_target(min_len, max_len)
        human = Game(target=word)
        agent = Game(target=word)
        race = Race(human_game=human, agent_game=agent, mode=mode, max_steps=max_steps)
        with self._lock:
            self.races[race.race_id] = race
        return race


_store: Optional[Store] = None
_lock = threading.Lock()


def get_store() -> Store:
    global _store
    with _lock:
        if _store is None:
            _store = Store(get_engine())
        return _store
