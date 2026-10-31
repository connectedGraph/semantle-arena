"""词池覆盖审计：常用词进没进池、被哪条规则挡住的。

用法
----
    python scripts/audit_pool.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_wordlist import (  # noqa: E402
    DEFAULT_KEEP_POS, load_rules, is_cjk,
)

# 一份「普通人会觉得这是常见词」的参照表。若大量缺失，说明口径有问题。
COMMON = """
苹果 香蕉 橘子 葡萄 西瓜 草莓 橘子 桃子 梨子 芒果 柠檬 樱桃
钢琴 吉他 小提琴 鼓 长笛 二胡 古筝 喇叭 音响 音乐 歌曲 旋律
电脑 手机 键盘 鼠标 屏幕 耳机 相机 电视 冰箱 空调 洗衣机 微波炉
医生 护士 老师 学生 警察 律师 厨师 司机 演员 歌手 作家 画家
足球 篮球 排球 网球 羽毛球 乒乓球 游泳 跑步 登山 滑雪 瑜伽 健身
开心 难过 生气 害怕 紧张 焦虑 兴奋 无聊 失望 后悔 尴尬 委屈
爱情 友情 亲情 婚姻 家庭 朋友 同事 邻居 陌生人 童年 青春 回忆
地铁 公交 火车 飞机 轮船 自行车 出租车 高铁 航班 车站 码头 机场
谎言 真话 秘密 承诺 借口 理由 梦想 目标 计划 习惯 性格 脾气
面包 蛋糕 馒头 米饭 面条 饺子 火锅 烧烤 咖啡 奶茶 啤酒 果汁
""".split()

# 明显不该进池的：短语、虚词组合、人名碎片
NOT_ANSWER = """
门外 有点 不在 省里 基本上 称得上 石榴石 珞狮 足足 寺里 铁甲
""".split()


def load_source(path: Path) -> dict[str, tuple[int, str]]:
    out = {}
    for line in path.open(encoding="utf-8"):
        p = line.split()
        if len(p) < 3:
            continue
        try:
            out[p[0]] = (int(p[1]), p[2])
        except ValueError:
            continue
    return out


def main() -> None:
    src = load_source(ROOT / "data" / "sources" / "jieba_dict.txt")
    rules = load_rules(ROOT / "data" / "wordlists" / "exclude.rules")
    pool = {w["w"] for w in json.loads(
        (ROOT / "data" / "wordlists" / "pool.json").read_text(encoding="utf-8"))["words"]}

    print(f"当前词池 {len(pool)} 词\n")

    print("== 常见词覆盖")
    missing = [w for w in dict.fromkeys(COMMON) if w not in pool]
    print(f"  {len(set(COMMON)) - len(missing)}/{len(set(COMMON))} 在池")
    if missing:
        print("  缺失:", " ".join(missing))
        print()
        print("  逐个查原因：")
        for w in missing:
            if w not in src:
                print(f"    {w:6s} 不在 jieba 词典")
                continue
            freq, pos = src[w]
            reasons = []
            if not (2 <= len(w) <= 4):
                reasons.append(f"字数 {len(w)}")
            if not is_cjk(w):
                reasons.append("非纯汉字")
            if pos not in DEFAULT_KEEP_POS:
                reasons.append(f"词性 {pos}")
            if freq < 200:
                reasons.append(f"词频 {freq} < 200")
            hit = [i for i, r in enumerate(rules) if r(w)]
            if hit:
                reasons.append(f"命中排除规则 #{hit}")
            print(f"    {w:6s} freq={freq:<6d} pos={pos:4s}  {'; '.join(reasons) or '?'}")

    print()
    print("== 不该进池的词")
    bad = [w for w in NOT_ANSWER if w in pool]
    print(f"  {len(bad)} 个仍残留", " ".join(bad) if bad else "(无)")

    print()
    print("== 排除规则实际拦了什么（抽样）")
    blocked = [w for w, (f, p) in src.items()
               if len(w) == 2 and is_cjk(w) and p in DEFAULT_KEEP_POS
               and f >= 200 and any(r(w) for r in rules)]
    print(f"  二字高频词被规则挡住 {len(blocked)} 个，抽样：")
    print("  " + " ".join(blocked[:60]))


if __name__ == "__main__":
    main()
