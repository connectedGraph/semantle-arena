# 词表构建来源与口径

本目录的 `pool.json` 是**可换词表**的产物，由 `scripts/build_wordlist.py` 生成。
换词表只需改这里的源文件并重跑构建，游戏逻辑不动。

## 当前口径（2026-10-31 定）

| 项 | 取值 |
|---|---|
| 主源 | jieba `dict.txt`（MIT，349046 条，带词频与词性），词频 ≥ 200 |
| 副源 | webdict（22 万条带词频），词频 ≥ 3000 |
| 字数 | 2 ~ 4 字，纯汉字 |
| 词性 | **只做硬排除**，不做正向白名单（理由见下） |
| 排除规则 | 方位后缀、虚词前缀、叠词、高频短语（`exclude.rules`），另有人工豁免 |

产出：22479 词（二字 18799 / 三字 3167 / 四字 483）。

## 三个走过弯路的口径决策

### 1. 词性白名单是错的

第一版按 `n / v / a / vn / ...` 白名单收词，结果把一大批常用词挡在外面：

| 词 | jieba 词性 | 实际是什么 |
|---|---|---|
| 西瓜 | `ns`（地名） | 水果 |
| 吉他 | `ns` | 乐器 |
| 登山 | `ns` | 运动 |
| 小提琴 | `nr`（人名） | 乐器 |
| 滑雪 | `nr` | 运动 |
| 相机 | `d`（副词） | 物品 |

jieba 的词性标注对短词不可靠。改成**只硬排除一定不是谜底的类别**
（人名 `nr*`、机构 `nt`、数词 `m`、量词 `q`、代词 `r`、虚词 `c/p/u/y/e/o`、
方位 `f`、成语 `i`、惯用语 `l`），其余全收，再靠词频和排除规则筛。

### 2. 单源不够，需要第二词源

jieba 的二字词频分布很陡：`橘子 87 / 草莓 116 / 芒果 125 / 奶茶 89`，
都低于 200 但都是日常词。webdict 的同一批词是 `橘子 9272 / 草莓 14349 / 芒果 7805`。

两个源词频量级完全不同，所以**每个源有自己的 `min_freq`**。

### 3. webdict 会把专名带进来

webdict 没有词性标注，`安德烈 / 塞尔维亚 / 中国 / 北京` 都在里面。
解法：用 jieba 的词性表做交叉校验——**若 jieba 有该词且标为专名/数词，就排除**。
这样 `中国/美国/北京` 被挡（正确），而 jieba 没收录的词照收。

### 4. 排除规则会误伤

第一版写了 `suffix:里 上 下 中 外 内 边 们 着 了 过 地 得 么`，
把 `难过 / 经过 / 通过` 全杀了（`难过` 词频 691，明显是常用词）。
改成只保留方位后缀，虚词组合改用 `exact` 逐个列。

另外叠词规则 `^(.)\1+$` 会杀掉 `星星 / 娃娃`，用 `allow:` 豁免。

## 换词表怎么做

`scripts/build_wordlist.py` 的 `DEFAULT_SOURCES` 是源列表，每个源独立配置：

```python
{
    "source": "jieba",
    "path": "data/sources/jieba_dict.txt",
    "format": "jieba",        # 词 词频 词性
    "min_freq": 200,
}
{
    "source": "webdict",
    "path": "data/sources/webdict.txt",
    "format": "freq",         # 词 词频
    "min_freq": 3000,
}
```

已支持 `format`：`jieba` / `freq` / `plain`（一行一词）。

```bash
# 试档位（不写文件）
python scripts/build_wordlist.py --min-freq 100 --dry-run
# 写文件并重建向量
python scripts/build_wordlist.py
python scripts/build_embeddings.py
# 复核常见词覆盖
python scripts/audit_pool.py
```

`audit_pool.py` 会报告「一份常见词参照表里哪些词没进池、被谁挡住的」，
是换词表后必跑的检查。

## 参考来源

| 源 | 许可 | 说明 |
|---|---|---|
| jieba `dict.txt` | MIT | 349046 条，带词频与词性，覆盖偏新闻语料 |
| webdict | CC BY-SA 3.0（词表部分源自 CC-CEDICT） | 22 万条带词频，2014 年新闻/豆瓣/财经语料统计 |
| THUOCL | 清华 THUNLP，学术使用 | 领域词表，适合做单领域模式（默认未并入） |
