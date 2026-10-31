"""检索质量基准：给定答案词，看它的真实上位/同域词排在什么位置。

这是判断「引擎能不能撑起一款猜词游戏」的核心指标——
如果连人类认为最相关的词都排不进前 50，游戏就不可玩。

用法
----
    ./.venv/bin/python tests/retrieval_bench.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from semantle.embedder import get_engine  # noqa: E402
from semantle.store import get_store  # noqa: E402
from semantle.models import Game  # noqa: E402

# 每个答案给出人类会先想到的几个词。命中越多、名次越靠前，引擎越好。
CASES = {
    "钢琴": ["音乐", "乐器", "弹奏", "乐曲", "小提琴", "演奏"],
    "苹果": ["水果", "香蕉", "橘子", "果树", "果汁"],
    "医生": ["医院", "大夫", "病人", "治病", "护士"],
    "足球": ["球队", "比赛", "篮球", "球员", "球场"],
    "冰箱": ["电器", "冷藏", "厨房", "空调", "保鲜"],
    "后悔": ["遗憾", "懊悔", "伤心", "难过", "内疚"],
    "地铁": ["火车", "公交", "车站", "高铁", "交通"],
    "谎言": ["说谎", "欺骗", "假话", "骗子", "真实"],
    "面包": ["蛋糕", "馒头", "早餐", "面粉", "烘焙"],
    "电脑": ["键盘", "鼠标", "手机", "软件", "显示器"],
}


def main() -> None:
    store = get_store()
    engine = store.engine
    total = hit10 = hit50 = hit200 = 0
    not_in_pool = out_of_range = 0
    detail: list[str] = []

    for target, probes in CASES.items():
        game = Game(target=target)
        store._prime(game)
        ranks = []
        for p in probes:
            r = game._ranks.get(p)
            ranks.append((p, r))
            total += 1
            if r is None:
                # 分不清「词池里没有」和「排名在 3000 之外」——两者含义完全不同：
                # 前者是词表覆盖问题，后者才是引擎排序问题。
                if store.engine.in_pool(p):
                    out_of_range += 1
                else:
                    not_in_pool += 1
                continue
            if r <= 10:
                hit10 += 1
            if r <= 50:
                hit50 += 1
            if r <= 200:
                hit200 += 1
        shown = ", ".join(
            f"{p}:{r if r else ('3000+' if store.engine.in_pool(p) else '缺')}"
            for p, r in ranks
        )
        avg = sum(r for _, r in ranks if r) / max(1, sum(1 for _, r in ranks if r))
        detail.append(f"{target:4s} 平均名次 {avg:6.0f}  {shown}")

    print(f"档位：{store.engine.tier}（{store.engine.size} 词）")
    print("答案 → 常识相关词的名次（越小越对；「缺」= 该词不在当前档位）")
    for line in detail:
        print("  " + line)

    in_pool = total - not_in_pool
    print()
    print(f"前 10 命中 {hit10}/{total} = {hit10 / total:.0%}")
    print(f"前 50 命中 {hit50}/{total} = {hit50 / total:.0%}")
    print(f"前 200 命中 {hit200}/{total} = {hit200 / total:.0%}")
    if not_in_pool:
        print(f"\n注：{not_in_pool}/{total} 个探针词不在谜底池，"
              f"{out_of_range} 个在池但排到 3000 之外")
        print(f"   只看在池的词，前 200 命中 {hit200}/{in_pool} = {hit200 / max(1, in_pool):.0%}")

    # 判定线：前 200 命中率过半，说明语义场是对的；前 50 有相当比例则体感可用
    denom = max(1, in_pool)
    ok = hit200 / denom >= 0.6 and hit50 / denom >= 0.3
    print()
    print("✓ 语义检索质量达标" if ok else "✗ 语义检索质量不足，需要调引擎")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
