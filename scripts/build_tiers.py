"""词库档位：small / medium / full。

核心问题
--------
「按词频取前 3000」得到的是 `策略 / 数量 / 反映 / 要求 / 全球性` ——
全是新闻语料的抽象高频词。玩家看到答案会想「这也能猜？」，
比冷门词更难，因为不知道往哪联想。

真正要的是**具象词**：能被指着说「这是个东西」的词。

具象度怎么量
------------
用「**这个词被多少个具象种子词当作近邻**」。
种子是一批无可争议的具象日常名词（苹果、钢琴、雨伞、蜜蜂……）。
如果「杯子」出现在「苹果」「蛋糕」「书桌」等十几个种子词的近邻里，
它就是具象词；如果「策略」只出现在「方案」「方法」的近邻里，它就不是。

这个方法的好处是不依赖词性标注（jieba 的 n 里混着 `问道/又称/眼见`）。
实测用它筛出来的全是 `杯子/蛋糕/沙发/勺子/椅子/蜡烛/镜子` 这类，肉眼可验。

三档
----
- small  3000：种子分最高的 3000 个，几乎全是日常具象词
- medium 8000：放宽到有任意具象近邻的词
- full   全量：词向量认识的词全收

用法
----
    python scripts/build_tiers.py
    python scripts/build_tiers.py --dry-run
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

from semantle.embedder import get_engine  # noqa: E402

TIERS_PATH = ROOT / "data" / "wordlists" / "tiers.json"

TIERS = {"small": 3000, "medium": 8000, "full": None}

# 具象种子：**按领域分组**，每组内数量接近。
# 为什么不给一个大列表：实测食物组给多了，前 30 名全是食物
# （面包/饼干/香蕉/薯条/薯片/三明治…），说明投票被种子分布带偏。
# 领域均衡才能真正覆盖游戏想要的那种「随机跳到任意领域」的体验。
SEED_GROUPS = {
    "食物": "苹果 香蕉 橘子 西瓜 草莓 面包 蛋糕 米饭 面条 饺子 咖啡 牛奶 啤酒 果汁".split(),
    "乐器": "钢琴 吉他 小提琴 鼓 二胡 长笛 歌曲 音乐 乐器".split(),
    "运动": "足球 篮球 排球 网球 羽毛球 乒乓球 游泳 跑步 滑雪 自行车".split(),
    "交通": "汽车 火车 飞机 轮船 地铁 公交 卡车 直升机".split(),
    "职业": "医生 护士 老师 学生 警察 律师 厨师 司机 演员 歌手 作家 画家".split(),
    "场所": "教室 医院 学校 图书馆 超市 餐厅 厨房 卧室 客厅 花园 公园 车站 机场".split(),
    "动物": "猫 狗 兔子 老虎 狮子 大象 猴子 熊猫 长颈鹿 斑马 企鹅 海豚 鲨鱼 乌龟 蝴蝶 蜜蜂".split(),
    "植物": "玫瑰 荷花 向日葵 仙人掌 蒲公英 樱花 竹子 柳树 松树 银杏 蘑菇 苔藓".split(),
    "电器": "冰箱 空调 洗衣机 电视 电脑 手机 相机 耳机 台灯 微波炉 吹风机".split(),
    "服饰": "雨伞 眼镜 帽子 手套 围巾 袜子 皮鞋 衬衫 裙子 书包 钱包 钥匙 手表 项链".split(),
    "自然": "月亮 太阳 星星 彩虹 云朵 雪花 闪电 火山 沙漠 瀑布 森林 海洋 河流 湖泊".split(),
    "家居": "蜡烛 镜子 椅子 桌子 沙发 书架 窗帘 地毯 花瓶 水杯 勺子 筷子 碗 盘子".split(),
    "情绪": "开心 难过 害怕 紧张 焦虑 兴奋 失望 后悔 尴尬 委屈 温柔 勇敢".split(),
    "抽象": "爱情 友情 童年 回忆 梦想 希望 秘密 谎言 承诺 习惯 性格 脾气".split(),
}

# 拼成扁平种子列表（保持分组顺序，构建时按组轮转计票以保证均衡）
SEEDS = [w for g in SEED_GROUPS.values() for w in g]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=str(TIERS_PATH))
    args = ap.parse_args()

    engine = get_engine()
    words = engine.words
    n = len(words)
    info = engine.all_info
    print(f"词池 {n} 词")

    # 按领域分组计票，组内归一化：每组总票权 = 1。
    # 不这样做的话，种子多的组（食物 14 个）会主导排名，
    # 实测前 30 名全是食物类。
    groups = {g: [w for w in ws if engine.in_pool(w)] for g, ws in SEED_GROUPS.items()}
    groups = {g: v for g, v in groups.items() if v}
    total_seeds = sum(len(v) for v in groups.values())
    print(f"具象种子 {total_seeds}/{len(set(SEEDS))} 在池，分 {len(groups)} 组")

    K = 250
    votes = np.zeros(n, dtype=np.float32)
    print(f"投票中（每个种子取前 {K} 近邻，按组归一化）…")
    done = 0
    for gname, gwords in groups.items():
        weight = 1.0 / len(gwords)          # 组内每个种子平分这一组的一票权
        for s in gwords:
            for w, _raw, _adj in engine.neighbors(s, k=K):
                votes[engine._index[w]] += weight
            done += 1
            if done % 40 == 0:
                print(f"  {done}/{total_seeds}", flush=True)

    order = np.argsort(-votes)
    print(f"得票：最多 {votes[order[0]]:.2f}，"
          f"≥0.05 的 {int((votes >= 0.05).sum())} 词，"
          f"≥0.5 的 {int((votes >= 0.5).sum())} 词")

    out: dict[str, list[str]] = {}
    for tier, size in TIERS.items():
        if size is None:
            picked = [w for w in words]
        else:
            ranked = [i for i in order if votes[i] > 0]
            # 票数相同按词频降序，避免把冷僻词排前面
            ranked.sort(key=lambda i: (-votes[i], -info[words[i]].freq if info.get(words[i]) else 0))
            picked = [words[i] for i in ranked[:size]]
        out[tier] = picked
        print(f"{tier:>7}: {len(picked)} 词  "
              f"（二字 {sum(1 for w in picked if len(w)==2)} / "
              f"三字 {sum(1 for w in picked if len(w)==3)} / "
              f"四字 {sum(1 for w in picked if len(w)==4)}）")

    if args.dry_run:
        print("（dry-run，未写文件）")
        return

    path = Path(args.out)
    path.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "method": "seed-neighbor-vote",
        "seed_groups": {g: len(v) for g, v in groups.items()},
        "neighbor_k": K,
        "tiers": {k: {"count": len(v)} for k, v in out.items()},
        "words": out,
    }, ensure_ascii=False), encoding="utf-8")
    print(f"已写入 {path} ({path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
