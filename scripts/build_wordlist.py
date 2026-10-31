"""词表构建：把多个来源编译成统一的谜底池 pool.json。

设计要点
--------
- 词池 = 「能当谜底的词」，只受词性 + 词频 + 字数约束，不需要向量模型。
  猜词不受此池限制（任意汉字表达都能算相似度），见 engine/embedder.py。
- 多源合并：同词取最高词频；每个词记录来源，便于排查。
- 输出 pool.json 之后，由 build_tiers.py 切出精简/标准/完整三档。

用法
----
    python scripts/build_wordlist.py                     # 用默认口径
    python scripts/build_wordlist.py --min-freq 200      # 试不同档位
    python scripts/build_wordlist.py --dry-run           # 只报规模
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "data" / "sources"
OUT = ROOT / "data" / "wordlists" / "pool.json"

# 词性过滤分两层，因为「能不能当谜底」和「是不是词」是两件事。
#
# 第一层 HARD_EXCLUDE_POS：一定不是谜底的类别，无论词频多高都排除。
#   人名 nr*、机构 nt、数词 m、量词 q、代词 r、虚词 c/p/u/y/e/o、方位 f、成语 i、惯用语 l
#
# 第二层：按品类给不同的词频门槛（见 POS_MIN_FREQ_MULT）。
#   为什么不能简单砍掉动词/形容词：`警察 / 后悔 / 害怕 / 开心 / 焦虑` 都是
#   很好的谜底（Semantle 原版也收情绪词），一律排除会把游戏抽空。
#   但把动词整片按低门槛收也不行——实测随机谜底抽到 `挂职 / 出资 / 增持 /
#   批准 / 打开 / 判断`，玩家没法靠「联想一个东西」逼近。
#   所以：高频的 v/a 收（信息量够、多数人认识），低频的直接丢。
#
# 不收 d（副词）：`也许 / 激烈 / 一直` 这类没有实体指称，任何词频都没法玩。
ANSWER_POS = {"n", "nz", "vn", "an", "s", "t", "b", "z"}
# 动词/形容词：只有足够高频才收（倍数作用于该源的 min_freq）
SOFT_POS = {"v", "a", "ad", "vd"}
# 绝对门槛而非倍数：两个源的词频量级差一个数量级，倍数没法同时适用。
# 400 这个值来自实测——`开心 487 / 焦虑 676 / 难过 691 / 后悔 988 / 尴尬 1430 /
# 警察 1677 / 兴奋 2575 / 害怕 3404 / 紧张 4790` 都在线上，而
# `挂职 / 出资 / 增持 / 批准` 这类在 200~400 之间，正好被挡掉。
SOFT_POS_MIN_FREQ = 400

HARD_EXCLUDE_POS = {
    "nr", "nrfg", "nrt", "nt", "m", "mq", "q", "r", "c", "p", "u",
    "y", "e", "o", "f", "i", "l", "zg", "eng", "x",
}
# 保留给 --strict-pos 用（更窄的白名单，仅供实验）
DEFAULT_KEEP_POS = {"n", "nz", "vn", "an", "s", "t", "b", "z"}

# 每个源可以有自己的 min_freq：不同来源的词频量级完全不同
# （jieba 的 200 是「比较常用」，webdict 的 200 是「几乎不出现」）
DEFAULT_SOURCES = [
    {
        "source": "jieba",
        "path": str(SOURCES / "jieba_dict.txt"),
        "format": "jieba",
        "min_freq": 200,
    },
    {
        # webdict 覆盖 jieba 漏掉的常用词（橘子 9272 / 吉他 9435 / 小提琴 3212），
        # 但它没有人名过滤，靠词频 + 排除规则兜。阈值按它的量级定。
        "source": "webdict",
        "path": str(SOURCES / "webdict.txt"),
        "format": "freq",
        "min_freq": 3000,
    },
]


def is_cjk(word: str) -> bool:
    return bool(word) and all("一" <= c <= "鿿" for c in word)


def read_jieba(path: Path):
    """词 词频 词性"""
    for line in path.open(encoding="utf-8"):
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            yield parts[0], int(parts[1]), parts[2]
        except ValueError:
            continue


def read_freq(path: Path):
    """词 词频"""
    for line in path.open(encoding="utf-8"):
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            yield parts[0], int(parts[1]), None
        except ValueError:
            continue


def read_plain(path: Path):
    """一行一词"""
    for i, line in enumerate(path.open(encoding="utf-8")):
        w = line.strip()
        if w and not w.startswith("#"):
            yield w, 1, None


READERS = {"jieba": read_jieba, "freq": read_freq, "plain": read_plain}
READ_JIEBA = read_jieba


def build(sources, min_freq: int, min_len: int, max_len: int,
          keep_pos: set[str], exclude: set[str],
          rules: Optional[list] = None,
          strict_pos: bool = False,
          allow: Optional[set] = None) -> dict:
    """编出词池。

    strict_pos=False（默认）：词性只做**硬排除**（HARD_EXCLUDE_POS），
      不做正向白名单。理由是 jieba 对短词的词性误标太常见，
      按白名单收会漏掉 `西瓜 / 吉他 / 小提琴 / 相机 / 登山` 这类常用词。
    strict_pos=True：只保留 keep_pos 里的词性，池子更干净但漏词更多。
    """
    merged: dict[str, dict] = {}
    stats: dict[str, int] = {}
    blocked = 0
    by_pos: dict[str, int] = {}

    # 参考词性表：先用带词性的源建一份全量 word -> pos，
    # 供无词性的源（webdict）交叉校验。否则 webdict 会把 `安德烈 / 塞尔维亚`
    # 这类专名带进谜底池。
    ref_pos: dict[str, str] = {}
    for spec in sources:
        if spec.get("format") != "jieba":
            continue
        for word, _freq, pos in READ_JIEBA(Path(spec["path"])):
            if pos:
                ref_pos[word] = pos

    for spec in sources:
        name = spec["source"]
        src_min = spec.get("min_freq", min_freq)
        path = Path(spec["path"])
        if not path.exists():
            print(f"  跳过 {name}：文件不存在 {path}", file=sys.stderr)
            continue
        reader = READERS.get(spec["format"])
        if reader is None:
            raise SystemExit(f"未知格式 {spec['format']}（可选 {list(READERS)}）")

        kept = 0
        for word, freq, pos in reader(path):
            if not (min_len <= len(word) <= max_len):
                continue
            if not is_cjk(word):
                continue
            if word in exclude:
                continue
            # allow 是人工复核过的豁免：同时绕过词性与排除规则
            soft = False
            if word in (allow or ()):
                pass
            elif pos is not None:
                pos = pos
            else:
                # 无词性的源（webdict）：借 jieba 的词性表判断。
                # jieba 没收录的默认不收——webdict 这类词里大量是短语句和专名
                # （`黄某 / 库区 / 新网 / 首款`），除非 allow 点名。
                pos = ref_pos.get(word)
                if pos is None:
                    continue

            if word not in (allow or ()):
                if strict_pos:
                    if pos not in keep_pos:
                        continue
                elif pos in HARD_EXCLUDE_POS:
                    continue
                elif pos in SOFT_POS:
                    soft = True
                elif pos not in ANSWER_POS:
                    continue

            # webdict 的目标是「补 jieba 漏掉的具象名词」，不是「再贡献一个词池」。
            # 实测它的高频区几乎全是财经/新闻语料词（安排 / 安全 / 安装 / 办理 /
            # 公司 / 市场 / 记者），当谜底没有可猜性，且把词池稀释得很快。
            # 所以对非 jieba 源的 vn/b/z/s/t 不收，只收 n / nz。
            if pos is not None and name != "jieba" and not soft:
                if pos not in {"n", "nz"}:
                    continue

            # 动词/形容词按更高门槛收：高频的（警察/后悔/害怕）留，低频的丢。
            # allow 点名的词不受词频门槛限制——它们是被人工确认为好谜底的
            # （内疚 194、弹奏 126 这类，词频低但确实是玩家想得到的词）。
            if word not in (allow or ()):
                need = max(src_min, SOFT_POS_MIN_FREQ) if soft else src_min
                if freq < need:
                    continue
            if rules and word not in (allow or ()) and any(rule(word) for rule in rules):
                blocked += 1
                continue
            kept += 1
            if pos:
                by_pos[pos] = by_pos.get(pos, 0) + 1
            prev = merged.get(word)
            if prev is None or freq > prev["freq"]:
                merged[word] = {"freq": freq, "pos": pos, "source": name}
            else:
                prev.setdefault("also", []).append(name)
        stats[name] = kept

    words = [{"w": w, **meta} for w, meta in merged.items()]
    words.sort(key=lambda x: (-x["freq"], x["w"]))

    by_len = {}
    for item in words:
        by_len[str(len(item["w"]))] = by_len.get(str(len(item["w"])), 0) + 1

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "params": {
            "min_freq": min_freq,
            "min_len": min_len,
            "max_len": max_len,
            "keep_pos": sorted(keep_pos),
            "strict_pos": strict_pos,
            "hard_exclude_pos": sorted(HARD_EXCLUDE_POS),
            "pos_dist": dict(sorted(by_pos.items(), key=lambda x: -x[1])[:12]),
            "exclude_count": len(exclude),
            "rule_blocked": blocked,
        },
        "sources": stats,
        "count": len(words),
        "by_length": by_len,
        "words": words,
    }


def load_rules(path: Path) -> list:
    """解析 exclude.rules，返回一组谓词函数。

    另有一条 `allow:` 规则用于「白名单豁免」——被其它规则挡住但确实是词的
    （如叠词里的 `星星 / 娃娃`）。它在 build() 里优先判断，所以这里把 allow
    也编成谓词，并让调用方用 load_allow() 单读它。
    """
    import re
    rules = []
    if not path.exists():
        return rules
    for raw in path.open(encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kind, _, body = line.partition(":")
        kind, body = kind.strip(), body.strip()
        if not body:
            continue
        if kind == "suffix":
            chars = tuple(body.split())
            rules.append(lambda w, c=chars: len(w) <= 4 and w[-1] in c)
        elif kind == "prefix":
            chars = tuple(body.split())
            rules.append(lambda w, c=chars: len(w) <= 4 and w[0] in c)
        elif kind == "pattern":
            rx = re.compile(body)
            rules.append(lambda w, r=rx: bool(r.match(w)))
        elif kind == "exact":
            words = frozenset(body.split())
            rules.append(lambda w, s=words: w in s)
        elif kind == "allow":
            continue   # 由 load_allow 单独读取
        else:
            raise SystemExit(f"未知规则类型 {kind}（可选 suffix/prefix/pattern/exact/allow）")
    return rules


def load_allow(path: Path) -> set[str]:
    """读 allow: 规则里的豁免词。"""
    out: set[str] = set()
    if not path.exists():
        return out
    for raw in path.open(encoding="utf-8"):
        line = raw.strip()
        if not line.startswith("allow:"):
            continue
        out.update(line.split(":", 1)[1].split())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-freq", type=int, default=200)
    ap.add_argument("--min-len", type=int, default=2)
    ap.add_argument("--max-len", type=int, default=4)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--strict-pos", action="store_true",
                    help="只保留白名单词性（更干净但会漏常用词）")
    args = ap.parse_args()

    exclude_path = ROOT / "data" / "wordlists" / "exclude.txt"
    exclude = set()
    if exclude_path.exists():
        exclude = {l.strip() for l in exclude_path.open(encoding="utf-8")
                   if l.strip() and not l.startswith("#")}

    rules_path = ROOT / "data" / "wordlists" / "exclude.rules"
    rules = load_rules(rules_path)
    allow = load_allow(rules_path)

    data = build(DEFAULT_SOURCES, args.min_freq, args.min_len, args.max_len,
                 DEFAULT_KEEP_POS, exclude, rules, strict_pos=args.strict_pos,
                 allow=allow)

    print(f"谜底池：{data['count']} 词  按字数 {data['by_length']}")
    print(f"来源：{data['sources']}  min_freq={args.min_freq}  "
          f"规则剔除 {data['params']['rule_blocked']}")
    if args.dry_run:
        print("（dry-run，未写文件）")
        return

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写入 {out}  ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
