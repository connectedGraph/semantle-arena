"""腾讯词向量 vs 其它向量模型的对比评测（结论已写进 docs/engine.md）。

问的问题：在**同一批候选词**上，哪个模型给出的「人类觉得相关」的排名更好？

这个脚本保留下来是为了让结论可复现——换任何向量模型时，用同一套探针
跑一遍就知道新模型值不值得换。

依赖 gensim 和 onnxruntime，**不是项目运行时依赖**。跑之前：
    python -m venv /tmp/eval && /tmp/eval/bin/pip install gensim onnxruntime tokenizers numpy
    /tmp/eval/bin/python tests/compare_embeddings.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path("/home/rap/workspace/categories/artifacts/semantle-arena")
TENCENT_DIR = Path("/home/rap/workspace/categories/artifacts/chinese-semantle/backend")

sys.path.insert(0, str(ROOT / "engine"))
from semantle.embedder import get_engine  # noqa: E402

# 每个答案给一组人类会想到的词。命中率越高、名次越靠前越好。
CASES = {
    "粘贴": ["黏贴", "胶水", "贴纸", "透明胶", "双面胶", "胶带"],
    "钢琴": ["音乐", "乐器", "小提琴", "吉他", "弹奏", "演奏"],
    "苹果": ["水果", "香蕉", "橘子", "果汁", "果树", "桃子"],
    "医生": ["医院", "大夫", "病人", "护士", "治病", "手术"],
    "足球": ["球队", "篮球", "球员", "球场", "比赛", "排球"],
    "冰箱": ["电器", "空调", "冷藏", "厨房", "洗衣机", "保鲜"],
    "后悔": ["遗憾", "懊悔", "难过", "伤心", "内疚", "失望"],
    "地铁": ["火车", "公交", "车站", "高铁", "交通", "列车"],
    "谎言": ["说谎", "欺骗", "假话", "骗子", "谎话", "谣言"],
    "面包": ["蛋糕", "馒头", "早餐", "面粉", "饼干", "烘焙"],
    "电脑": ["键盘", "鼠标", "手机", "显示器", "软件", "主机"],
    "雨伞": ["雨衣", "下雨", "雨靴", "晴天", "遮阳", "伞"],
}


def main() -> None:
    from gensim.models import KeyedVectors

    print("加载腾讯词向量…")
    kv = KeyedVectors.load(str(TENCENT_DIR / "data" / "embedding.kv"))

    print("加载词向量引擎…")
    engine = get_engine()
    words = engine.words
    matrix = engine.matrix
    idx = {w: i for i, w in enumerate(words)}
    print(f"  引擎 {engine.meta['engine']}，{len(words)} 词，{matrix.shape[1]} 维")

    # 只比两者都认识的候选词
    stats = {"tencent": {"hit10": 0, "hit50": 0, "hit200": 0, "total": 0, "miss": 0},
             "wordvec": {"hit10": 0, "hit50": 0, "hit200": 0, "total": 0, "miss": 0}}

    print()
    print(f"{'答案':<6} {'探针':<6} {'腾讯名次':>10} {'词向量名次':>10}")
    print("-" * 42)

    for target, probes in CASES.items():
        if target not in kv.key_to_index:
            print(f"{target} 不在腾讯词向量")
            continue

        # 腾讯：在词池范围内排序
        t_scores = []
        for w in words:
            if w in kv.key_to_index:
                t_scores.append((w, float(kv.similarity(target, w))))
        t_scores.sort(key=lambda x: -x[1])
        t_rank = {w: i + 1 for i, (w, _) in enumerate(t_scores)}

        # 当前词向量引擎
        w_idx = idx[target]
        sims = matrix @ matrix[w_idx]
        order = np.argsort(-sims)
        w_rank = {words[j]: r + 1 for r, j in enumerate(order)}

        for p in probes:
            tr = t_rank.get(p) if p in kv.key_to_index else None
            br = w_rank.get(p)
            if tr is None:
                stats["tencent"]["miss"] += 1
            if br is None:
                stats["wordvec"]["miss"] += 1
            stats["tencent"]["total"] += 1
            stats["wordvec"]["total"] += 1
            if tr and tr <= 10:
                stats["tencent"]["hit10"] += 1
            if br and br <= 10:
                stats["wordvec"]["hit10"] += 1
            if tr and tr <= 50:
                stats["tencent"]["hit50"] += 1
            if br and br <= 50:
                stats["wordvec"]["hit50"] += 1
            if tr and tr <= 200:
                stats["tencent"]["hit200"] += 1
            if br and br <= 200:
                stats["wordvec"]["hit200"] += 1
            print(f"{target:<6} {p:<6} {tr if tr else '缺':>10} {br if br else '缺':>10}")

    print()
    print(f"{'':14} {'腾讯':>10} {'词向量':>10}")
    for k, label in [("hit10", "前10命中"), ("hit50", "前50命中"), ("hit200", "前200命中")]:
        t = stats["tencent"][k]
        b = stats["wordvec"][k]
        tot = stats["tencent"]["total"]
        print(f"{label:14} {t:>4}/{tot:<5} {b:>4}/{tot:<5}")


if __name__ == "__main__":
    main()
