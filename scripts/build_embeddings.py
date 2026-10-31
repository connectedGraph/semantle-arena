"""离线构建：词池向量 + 每词 Top-K 邻居。

为什么离线
----------
在线为 1.4 万词算邻居要几十毫秒，对局里每个谜底都要一次；
预计算后启动只 load 两个矩阵，猜词是纯点积，单次 < 2ms。

字符重叠矩阵一次性算好（N×N 布尔交集计数），
这样邻居排序分数 = 语义相似度 - 惩罚 * 重叠比例，是两次矩阵运算。

产出
----
data/vectors/pool_vectors.npy   (N, 768) float32，L2 归一化
data/vectors/neighbors.npz      idx (N,K) int32 / score (N,K) float32
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from semantle.embedder import (  # noqa: E402
    DEFAULT_ONNX, DEFAULT_TOKENIZER, VECTORS_PATH, Embedder, load_config,
)

NEIGHBORS_PATH = ROOT / "data" / "vectors" / "neighbors.npz"


def build_overlap(words: list[str], dtype=np.float32) -> np.ndarray:
    """N×N 的共享汉字比例矩阵（按较短词计）。"""
    n = len(words)
    chars = sorted({c for w in words for c in w})
    col = {c: i for i, c in enumerate(chars)}
    # 词 × 汉字 的布尔矩阵
    B = np.zeros((n, len(chars)), dtype=bool)
    for i, w in enumerate(words):
        for c in w:
            B[i, col[c]] = True
    inter = (B.astype(np.float32) @ B.astype(np.float32).T)
    lengths = np.array([len(set(w)) for w in words], dtype=np.float32)
    denom = np.minimum(lengths[:, None], lengths[None, :])
    np.maximum(denom, 1, out=denom)
    return (inter / denom).astype(dtype)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=3000)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--skip-vectors", action="store_true",
                    help="向量已存在时跳过多余编码")
    ap.add_argument("--chunk", type=int, default=256,
                    help="邻居计算的块大小（控制内存）")
    args = ap.parse_args()

    pool = json.loads((ROOT / "data/wordlists/pool.json").read_text(encoding="utf-8"))
    words = [w["w"] for w in pool["words"]]
    n = len(words)
    print(f"词池 {n}（min_freq={pool['params']['min_freq']}）", flush=True)

    if args.skip_vectors and VECTORS_PATH.exists():
        matrix = np.load(VECTORS_PATH).astype(np.float32)
        if matrix.shape[0] != n:
            raise SystemExit(f"向量行数 {matrix.shape[0]} 与词池 {n} 不符，去掉 --skip-vectors")
        print(f"复用已有向量 {matrix.shape}", flush=True)
    else:
        emb = Embedder(DEFAULT_ONNX, DEFAULT_TOKENIZER, threads=args.threads)
        t0 = time.time()
        chunks = []
        for i in range(0, n, args.batch):
            chunks.append(emb.encode(words[i:i + args.batch]))
            done = min(i + args.batch, n)
            if done % (args.batch * 5) == 0 or done == n:
                print(f"  编码 {done}/{n}  {time.time() - t0:.0f}s", flush=True)
        matrix = np.vstack(chunks)
        VECTORS_PATH.parent.mkdir(parents=True, exist_ok=True)
        np.save(VECTORS_PATH, matrix)
        print(f"向量 {matrix.shape} → {VECTORS_PATH} "
              f"({VECTORS_PATH.stat().st_size / 1e6:.0f} MB)", flush=True)

    print("计算字符重叠矩阵…", flush=True)
    t0 = time.time()
    overlap = build_overlap(words)
    print(f"重叠矩阵 {overlap.shape} {time.time() - t0:.1f}s", flush=True)

    cfg = load_config()
    penalty, blend = cfg["char_penalty"], cfg["semantic_blend"]
    k = min(args.top_k, n - 1)
    idx = np.empty((n, k), dtype=np.int32)
    sco = np.empty((n, k), dtype=np.float32)

    print("逐块取 Top-K…", flush=True)
    t0 = time.time()
    for start in range(0, n, args.chunk):
        stop = min(start + args.chunk, n)
        sims = matrix[start:stop] @ matrix.T                     # (c, N)
        adj = blend * sims - penalty * overlap[start:stop]       # (c, N)
        rows = np.arange(stop - start)
        adj[rows, np.arange(start, stop)] = 1.0                  # 自己是满分
        part = np.argpartition(-adj, k, axis=1)[:, :k]
        part_scores = np.take_along_axis(adj, part, axis=1)
        order = np.argsort(-part_scores, axis=1)
        idx[start:stop] = np.take_along_axis(part, order, axis=1)
        sco[start:stop] = np.take_along_axis(part_scores, order, axis=1)
        if start % (args.chunk * 10) == 0:
            print(f"  {stop}/{n}  {time.time() - t0:.0f}s", flush=True)

    np.savez(out := NEIGHBORS_PATH, idx=idx, score=sco)
    print(f"邻居表 idx={idx.shape} → {out} ({out.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
