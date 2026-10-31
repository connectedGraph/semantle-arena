"""语义引擎：腾讯 AI Lab 中文词向量。

为什么是腾讯词向量，不是 BGE
----------------------------
我一度换成了 BGE 句向量（理由是「腾讯词向量缺新词」），实测后发现那个理由站不住，
而且 BGE 在猜词这个场景下明显更差。同题对照（12 个答案 × 6 个「人类会想到的词」）：

| 指标 | 腾讯词向量 | BGE |
|---|---|---|
| 前 10 命中 | **58%** | 30% |
| 前 50 命中 | **86%** | 68% |
| 前 200 命中 | **92%** | 82% |

差距最大的例子：`面包 → 蛋糕`（腾讯第 8，BGE 第 357）、
`电脑 → 显示器`（腾讯第 6，BGE 第 421）、`面包 → 饼干`（第 2 vs 第 152）。

根因是**词向量和句向量的语义粒度不同**。词向量是在大规模语料上按共现统计出来的，
「面包」和「蛋糕」经常出现在同一批上下文里；BGE 是句级编码器，
短词输入时它更依赖字面形态和句子级的抽象语义，
于是给出一堆抽象近义词——「粘贴」的最近邻是 `黏贴/黏合/黏连/粘合/粘结`，
全是同一个词的变体，玩家会觉得语义空间被同族词挤满。

对照腾讯词向量在同一位置的近邻：`胶水/胶带/打印/填充/拼接/铁丝/焊接`——
都是**具体的东西**，领域在跳跃，这才是猜词游戏想要的语义结构。

OOV 怎么处理
------------
腾讯词向量 14.3 万词，池内覆盖 90.3%。池外词（含任意表达）用字的向量平均近似：
组成词的每个汉字在表里就取它的向量求平均。这让「猜词不限」仍然成立，
只是池外词只有近似语义，会在结果里标 `approx=True`。

为什么保留字符重叠惩罚
----------------------
词向量也有同字干扰，只是比 BGE 轻得多。惩罚项保留，系数从 0.15 降到 0.06，
用于处理「粘贴 vs 黏贴」这类同字变体，不影响正常的语义近邻。

工程实现
--------
`embedding.kv` 是 gensim KeyedVectors 格式（200 维 float32）。
为了不在运行时依赖 gensim，这里直接读它的 `.vectors.npy` 与 `.kv` 里的键表，
用 numpy 做点积。启动时把选中的词向量拼成一个矩阵，O(1) 查表。
"""
from __future__ import annotations

import json
import logging
import pickle
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"
POOL_PATH = DATA / "wordlists" / "pool.json"
TIERS_PATH = DATA / "wordlists" / "tiers.json"

# 腾讯词向量：主文件 .kv（gensim 元数据）+ .vectors.npy（矩阵）
KV_DIR = DATA / "wordvectors"
KV_FILE = KV_DIR / "embedding.kv"
KV_VECTORS = KV_DIR / "embedding.kv.vectors.npy"

CONFIG_PATH = DATA / "engine_config.json"
DEFAULT_CONFIG = {"char_penalty": 0.06, "semantic_blend": 1.0}

# 档位名 -> tiers.json 里的键。None 表示用全池。
TIER_ALIASES = {"small": "small", "medium": "medium", "full": "full",
                "精简": "small", "标准": "medium", "完整": "full"}


@dataclass
class WordInfo:
    word: str
    freq: int
    pos: Optional[str]


class WordVectors:
    """腾讯词向量的最小读取器（不依赖 gensim 运行时）。"""

    def __init__(self, kv_file: Path = KV_FILE, vec_file: Path = KV_VECTORS) -> None:
        if not vec_file.exists():
            raise FileNotFoundError(
                f"缺少词向量 {vec_file}\n"
                f"把 chinese-semantle/backend/data/embedding.kv* 拷到 {KV_DIR}/，"
                f"或跑 ./install.sh 下载"
            )
        self.matrix = np.load(vec_file, mmap_mode="r")
        # .kv 是 gensim KeyedVectors 的 pickle。为了不在运行时依赖 gensim，
        # 这里只取出它的 key_to_index；若环境里没有 gensim，反序列化会失败，
        # 那时退回读同目录的 keys.txt（install.sh 会顺手生成）。
        index: Dict[str, int]
        try:
            with open(kv_file, "rb") as f:
                meta = pickle.load(f)
            index = dict(meta.key_to_index)
        except Exception:  # noqa: BLE001 —— 缺 gensim 或格式不符
            # 键表命名：embedding.kv -> embedding.kv.keys.txt
            # （不能用 with_suffix，那会把 .kv 整个替换掉）
            keys_file = kv_file.parent / (kv_file.name + ".keys.txt")
            if not keys_file.exists():
                raise RuntimeError(
                    f"无法解析 {kv_file}（需要 gensim），且没有备用键表 {keys_file}"
                )
            index = {line.rstrip("\n"): i
                     for i, line in enumerate(keys_file.open(encoding="utf-8"))}
        self.key_to_index = index
        self.dim = int(self.matrix.shape[1])
        logger.info("词向量 %d 词 × %d 维", len(index), self.dim)

    def __contains__(self, word: str) -> bool:
        return word in self.key_to_index

    def get(self, word: str) -> Optional[np.ndarray]:
        i = self.key_to_index.get(word)
        if i is None:
            return None
        return np.asarray(self.matrix[i], dtype=np.float32)

    def mean_of_chars(self, word: str) -> Optional[np.ndarray]:
        """池外词：用组成汉字的向量平均近似。任一汉字不在表里就返回 None。"""
        vecs = [self.get(ch) for ch in word]
        if not vecs or any(v is None for v in vecs):
            return None
        v = np.mean(vecs, axis=0)
        n = np.linalg.norm(v)
        return (v / n).astype(np.float32) if n > 1e-9 else None


class Engine:
    """游戏引擎：按档位取词、算相似度与名次。"""

    def __init__(self, tier: str = "full") -> None:
        if not POOL_PATH.exists():
            raise FileNotFoundError(f"缺少词池 {POOL_PATH}，先跑 scripts/build_wordlist.py")
        raw = json.loads(POOL_PATH.read_text(encoding="utf-8"))
        self.pool_meta = {k: raw[k] for k in
                          ("generated_at", "params", "sources", "count", "by_length")}
        all_words = [w["w"] for w in raw["words"]]
        self.all_info: Dict[str, WordInfo] = {
            w["w"]: WordInfo(w["w"], w.get("freq", 0), w.get("pos")) for w in raw["words"]
        }

        self.vectors = WordVectors()
        self._cfg = self._load_config()
        self._tiers = self._load_tiers()

        # 只保留词向量认识的词；这是所有档位的基础池
        self.coverage = [w for w in all_words if w in self.vectors]
        self.tier = self._normalize_tier(tier)
        self._words: List[str] = []
        self._index: Dict[str, int] = {}
        self._matrix: Optional[np.ndarray] = None
        self._chars: Dict[str, frozenset] = {}
        self.set_tier(self.tier)

    # ---------- 档位 ----------

    @staticmethod
    def _normalize_tier(tier: str) -> str:
        t = TIER_ALIASES.get(tier)
        if t is None:
            raise ValueError(f"未知档位 {tier}（可选 {'/'.join(TIER_ALIASES)}）")
        return t

    def _load_tiers(self) -> Dict[str, List[str]]:
        if not TIERS_PATH.exists():
            logger.warning("没有 tiers.json，所有档位都用全池")
            return {}
        raw = json.loads(TIERS_PATH.read_text(encoding="utf-8"))
        return raw.get("words", {})

    def available_tiers(self) -> Dict[str, int]:
        """前端展示用：[{key, count}]。"""
        if not self._tiers:
            return {"full": len(self.coverage)}
        return {k: len(v) for k, v in self._tiers.items()}

    def set_tier(self, tier: str) -> None:
        tier = self._normalize_tier(tier)
        if self._tiers.get(tier):
            allowed = [w for w in self._tiers[tier] if w in self.vectors]
        else:
            allowed = self.coverage
        if not allowed:
            raise ValueError(f"档位 {tier} 没有可用词")

        self.tier = tier
        self._words = allowed
        self._index = {w: i for i, w in enumerate(allowed)}
        self._chars = {w: frozenset(w) for w in allowed}
        # 拼成连续矩阵，猜词时一次点积
        self._matrix = np.vstack([self.vectors.get(w) for w in allowed]).astype(np.float32)
        norms = np.linalg.norm(self._matrix, axis=1, keepdims=True)
        self._matrix = self._matrix / np.clip(norms, 1e-9, None)
        logger.info("档位 %s：%d 词", tier, len(allowed))

    # ---------- 配置 ----------

    @staticmethod
    def _load_config() -> dict:
        cfg = dict(DEFAULT_CONFIG)
        if CONFIG_PATH.exists():
            try:
                cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                logger.warning("engine_config.json 解析失败，用默认值")
        return cfg

    # ---------- 查询 ----------

    @property
    def words(self) -> List[str]:
        return self._words

    @property
    def matrix(self) -> np.ndarray:
        assert self._matrix is not None
        return self._matrix

    @property
    def size(self) -> int:
        return len(self._words)

    @property
    def config(self) -> dict:
        return self._cfg

    @property
    def meta(self) -> dict:
        """给 /api/meta 用。"""
        by_len: Dict[str, int] = {}
        for w in self._words:
            by_len[str(len(w))] = by_len.get(str(len(w)), 0) + 1
        return {
            "generated_at": self.pool_meta["generated_at"],
            "params": self.pool_meta["params"],
            "sources": self.pool_meta["sources"],
            "count": len(self._words),
            "pool_total": self.pool_meta["count"],
            "by_length": by_len,
            "tier": self.tier,
            "tiers": self.available_tiers(),
            "vector_coverage": round(len(self.coverage) / max(1, self.pool_meta["count"]), 3),
            "engine": "tencent-word2vec-200d",
        }

    def in_pool(self, word: str) -> bool:
        return word in self._index

    def info(self, word: str) -> Optional[WordInfo]:
        return self.all_info.get(word)

    def vector(self, word: str) -> Tuple[Optional[np.ndarray], bool]:
        """返回 (向量, 是否为池外近似)。池内精确；池外用汉字平均近似。"""
        i = self._index.get(word)
        if i is not None:
            return self._matrix[i], False
        v = self.vectors.get(word)
        if v is not None:
            n = np.linalg.norm(v)
            return (v / n if n > 1e-9 else v), False
        approx = self.vectors.mean_of_chars(word)
        return approx, True

    def raw_similarity(self, target_vec: np.ndarray, word: str) -> Tuple[float, bool]:
        vec, approx = self.vector(word)
        if vec is None:
            return 0.0, True
        return float(np.dot(target_vec, vec)), approx

    def adjusted(self, target: str, word: str, raw: float) -> float:
        """加入字符重叠惩罚后的排序分。仅用于排名，不改原始相似度。"""
        if word == target:
            return 1.0
        penalty = self._cfg["char_penalty"]
        blend = self._cfg["semantic_blend"]
        return blend * raw - penalty * char_overlap(target, word)

    def neighbors(self, target: str, k: int = 3000) -> List[Tuple[str, float, float]]:
        """[(词, 原始相似度, 排序分)]，按排序分降序。"""
        vec, _ = self.vector(target)
        if vec is None:
            return []
        raw = self._matrix @ vec
        ch_t = self._chars.get(target, frozenset(target))
        overlaps = np.fromiter(
            (len(ch_t & self._chars[w]) / max(1, min(len(ch_t), len(self._chars[w])))
             for w in self._words),
            dtype=np.float32, count=len(self._words),
        )
        adj = self._cfg["semantic_blend"] * raw - self._cfg["char_penalty"] * overlaps
        i = self._index.get(target)
        if i is not None:
            adj[i] = 1.0
        k = min(k, len(adj))
        part = np.argpartition(-adj, k - 1)[:k]
        part = part[np.argsort(-adj[part])]
        return [(self._words[j], float(raw[j]), float(adj[j])) for j in part]


def char_overlap(a: str, b: str) -> float:
    """共享汉字比例（按较短词计）。`粘贴` vs `黏贴` = 0.5。"""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(1, min(len(sa), len(sb)))


_engine: Optional[Engine] = None
_lock = threading.Lock()


def get_engine() -> Engine:
    global _engine
    with _lock:
        if _engine is None:
            import os
            _engine = Engine(tier=os.environ.get("ARENA_TIER", "small"))
    return _engine
