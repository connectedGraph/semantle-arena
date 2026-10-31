"""语义引擎：BGE 中文句向量 + 字符干扰抑制。

为什么不是词向量表
------------------
原项目用的腾讯词向量只有 14.3 万词，且常用二字词覆盖有明显缺口
（`披萨`、`长颈鹿`、`贝多芬`、`躺平`、`社畜` 都不在），无法支撑「猜词不限」。
BGE 是 BERT 系编码器，对**任何**汉字串都能出向量，不存在 OOV。

为什么需要字符重叠惩罚
----------------------
实测 bge-base-zh-v1.5 在「钢琴」上给出 `弹琴/钢笔/钢铁/钢板/钢材`，
在「冰箱」上给出 `箱子/油箱/集装箱`，「大夫」上给出 `大丈夫/一夫/姐夫`——
字形相同但语义无关的词会挤掉真正的语义近邻。加一个按共享汉字比例线性扣分的项后，
`钢琴 → 音乐/乐器/弹奏`、`大夫 → 医生`、`冰箱 → 冷冻/电器`，肉眼可辨地正确。

两个可调参数（config.json）
--------------------------
- `char_penalty`：共享汉字比例每 100% 扣掉多少相似度，默认 0.15
- `semantic_blend`：完全不做惩罚的语义权重保留，默认 1.0

相似度口径
----------
对外输出的 `similarity` 是余弦相似度（-1~1），惩罚项只作用于**排名与展示**，
不改变原始语义分，便于排查。
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"
POOL_PATH = DATA / "wordlists" / "pool.json"
VECTORS_PATH = DATA / "vectors" / "pool_vectors.npy"
MODEL_DIR = DATA / "model"
DEFAULT_ONNX = MODEL_DIR / "model_base_int8.onnx"
DEFAULT_TOKENIZER = MODEL_DIR / "base_tokenizer.json"
CONFIG_PATH = DATA / "engine_config.json"

DEFAULT_CONFIG = {"char_penalty": 0.15, "semantic_blend": 1.0}


@dataclass
class WordInfo:
    word: str
    freq: int
    pos: Optional[str]


class Embedder:
    """BGE 编码器封装。线程安全（onnxruntime 会话本身可并发）。"""

    def __init__(self, onnx_path: Path = DEFAULT_ONNX,
                 tokenizer_path: Path = DEFAULT_TOKENIZER,
                 threads: int = 4, max_len: int = 16) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        if not onnx_path.exists():
            raise FileNotFoundError(
                f"缺少模型文件 {onnx_path}，先跑 ./install.sh 下载"
            )
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(onnx_path), providers=["CPUExecutionProvider"], sess_options=so
        )
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.tokenizer.enable_truncation(max_len)
        # 必须开启 padding：批内词长不一，否则 encode_batch 返回变长序列无法堆成矩阵
        self.tokenizer.enable_padding(length=max_len, pad_id=0, pad_token="[PAD]")
        self.max_len = max_len
        self._lock = threading.Lock()

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """返回 L2 归一化后的 (n, dim) 矩阵。空串按占位符处理。"""
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        clean = [t if t.strip() else "。 " for t in texts]
        enc = self.tokenizer.encode_batch(clean)
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        out = self.session.run(
            None,
            {
                "input_ids": ids,
                "attention_mask": mask,
                "token_type_ids": np.zeros_like(ids),
            },
        )[0]
        m = mask[..., None].astype(np.float32)
        vec = (out * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
        norm = np.linalg.norm(vec, axis=1, keepdims=True)
        return (vec / np.clip(norm, 1e-9, None)).astype(np.float32)


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            logger.warning("engine_config.json 解析失败，用默认值")
    return cfg


def char_overlap(a: str, b: str) -> float:
    """共享汉字比例（按较短词计）。`钢琴` vs `钢笔` = 0.5。"""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(1, min(len(sa), len(sb)))


class Engine:
    """游戏引擎：谜底池、向量矩阵、相似度与排名。"""

    def __init__(self, embedder: Optional[Embedder] = None) -> None:
        if not POOL_PATH.exists():
            raise FileNotFoundError(f"缺少词池 {POOL_PATH}，先跑 scripts/build_wordlist.py")
        raw = json.loads(POOL_PATH.read_text(encoding="utf-8"))
        self.meta = {k: raw[k] for k in ("generated_at", "params", "sources", "count", "by_length")}
        self.words: List[str] = [w["w"] for w in raw["words"]]
        self.info: Dict[str, WordInfo] = {
            w["w"]: WordInfo(w["w"], w.get("freq", 0), w.get("pos")) for w in raw["words"]
        }
        self._index: Dict[str, int] = {w: i for i, w in enumerate(self.words)}
        self._cfg = load_config()
        self.embedder = embedder or Embedder()
        self.matrix = self._load_matrix()
        self._chars = {w: frozenset(w) for w in self.words}

    # ---------- 向量矩阵 ----------

    def _load_matrix(self) -> np.ndarray:
        if VECTORS_PATH.exists():
            m = np.load(VECTORS_PATH)
            if m.shape[0] == len(self.words):
                return m
            logger.warning("向量矩阵行数 %d 与词池 %d 不符，重新计算", m.shape[0], len(self.words))
        logger.info("正在为 %d 个词计算向量（首次启动较慢，之后从缓存读）", len(self.words))
        return self.compute_matrix()

    def compute_matrix(self, batch: int = 512) -> np.ndarray:
        chunks = []
        for i in range(0, len(self.words), batch):
            chunks.append(self.embedder.encode(self.words[i:i + batch]))
        return np.vstack(chunks)

    def save_matrix(self, matrix: np.ndarray) -> None:
        VECTORS_PATH.parent.mkdir(parents=True, exist_ok=True)
        np.save(VECTORS_PATH, matrix)

    # ---------- 查询 ----------

    @property
    def size(self) -> int:
        return len(self.words)

    @property
    def config(self) -> dict:
        return self._cfg

    def in_pool(self, word: str) -> bool:
        return word in self._index

    def vector(self, word: str) -> np.ndarray:
        """池内词取缓存向量；池外词实时编码（支撑「猜词不限」）。"""
        if word in self._index:
            return self.matrix[self._index[word]]
        return self.embedder.encode([word])[0]

    def raw_similarity(self, target_vec: np.ndarray, word: str) -> float:
        return float(np.dot(target_vec, self.vector(word)))

    def adjusted(self, target: str, word: str, raw: float,
                 target_vec: Optional[np.ndarray] = None) -> float:
        """加入字符重叠惩罚后的排序分。仅用于排名/展示梯度。"""
        penalty = self._cfg["char_penalty"]
        blend = self._cfg["semantic_blend"]
        if word == target:
            return 1.0
        overlap = char_overlap(target, word)
        return blend * raw - penalty * overlap

    def neighbors(self, target: str, k: int = 3000) -> List[Tuple[str, float, float]]:
        """返回 [(词, 原始相似度, 排序分)]，按排序分降序。"""
        vec = self.vector(target)
        raw = self.matrix @ vec
        chars_t = self._chars.get(target, frozenset(target))
        penalty = self._cfg["char_penalty"]
        blend = self._cfg["semantic_blend"]
        # 向量化计算字符重叠，避免 1.4 万次 Python 循环
        overlaps = np.fromiter(
            (len(chars_t & self._chars[w]) / max(1, min(len(chars_t), len(self._chars[w])))
             for w in self.words),
            dtype=np.float32, count=len(self.words),
        )
        adj = blend * raw - penalty * overlaps
        if target in self._index:
            adj[self._index[target]] = 1.0
        top = np.argpartition(-adj, min(k, len(adj) - 1))[:k]
        top = top[np.argsort(-adj[top])]
        return [(self.words[j], float(raw[j]), float(adj[j])) for j in top]


_engine: Optional[Engine] = None
_lock = threading.Lock()


def get_engine() -> Engine:
    global _engine
    with _lock:
        if _engine is None:
            _engine = Engine()
    return _engine
