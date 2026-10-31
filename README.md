# Semantle Arena · 人机语义猜词对抗

> 你和 Agent 拿到同一个隐藏中文词，比谁用更少的回合猜中。

---

## 这是什么

一个中文语义猜词游戏（Semantle 玩法：每次猜词返回它和答案的语义相似度与名次），
加上一个**信息受限的 Agent 对手**：它看不到答案，只有两个工具——
批量猜词和回顾自己的战绩。

```
┌─────────────────┬─────────────────┐
│   你的猜测       │   Agent 的猜测   │
│                  │                 │
│ 音乐   1  76.60% │ 钢琴   1 100.00% │  ← 猜中
│ 小提琴 6  80.18% │ 音乐   1  76.60% │
│ 歌曲  31  69.46% │ 乐器   2  76.11% │
│ 医生  88  67.72% │ 歌手  22  69.95% │
│   3 回合         │   2 回合        │
└─────────────────┴─────────────────┘
              Agent 赢了
```

## 快速开始

```bash
./install.sh        # 依赖 + 模型(98MB) + 词表 + 向量 + 前端
./run.sh            # → http://127.0.0.1:8010
```

首次安装约 5 分钟（主要是 98MB 模型下载和 2.2 万词编码）。
`install.sh` 在 HuggingFace 不通时自动切 `hf-mirror`。

Agent 需要一个 OpenAI 兼容的模型服务：

```bash
cp .env.example .env
# 默认指向本机网关；改成 DeepSeek 官方：
#   ARENA_LLM_BASE_URL=https://api.deepseek.com/v1
#   ARENA_LLM_API_KEY=sk-...
```

## 它解决的两个问题

这不是又一个 Semantle 复刻。它是针对**上一版**（我 fork 的 `chinese-semantle-agent`）
两处硬伤的重写：

### 词表随意 → 统计口径

上一版是 1897 个人工堆的「具象名词」，实际把整片近义词群一起收进谜底池：

| 词群 | 同池词数 | 例子 |
|---|---|---|
| 风 | 19 | 清风 / 寒风 / 北风 / 东风 / 风光 / 风景 / 风味 / 风韵 / 风采 / 风尚 / 风雪 / 风雨 / 风云 / 风沙 / 风暴 / 风浪 / 狂风 / 旋风 / 飓风 |
| 山 | 10 | 高山 / 深山 / 山野 / 山间 / 山顶 / 山丘 / 山林 / 山河 |
| 舰船 | 9 | 巡洋舰 / 驱逐舰 / 护卫舰 / 航空母舰 / 核潜艇 / 潜艇 / 战船 / 旗舰 |

抽中「风韵」时同簇 18 个词全是高相似度，难度被词表本身污染了。
而且它自己的 `blacklist_memo.txt` 写着「涉军词一律不进」，而 `航空母舰 / 核潜艇`
都在池里。

本版从 jieba + webdict 双源按词性/词频/字数/排除规则编译，**不靠人工审美**。
详见 [词表构建](./data/wordlists/README.md)。

### 词向量覆盖不全 → 句向量

腾讯词向量 14.3 万词，`披萨 / 长颈鹿 / 贝多芬 / 躺平 / 社畜` 都不在，
猜这些词直接报「不在词表」。

换成 BGE 中文句向量（int8 ONNX，98MB，纯 CPU，无需 torch），
**任何汉字串都能编码**——这支撑了「猜词不限」。

## 三个设计决定

**1. 谜底受限，猜词不限。**
谜底从 2.2 万词的品质池里抽，但你输入什么都能算相似度。
猜「干饭搭子」这种词池里没有的表达也照常工作。

**2. 胜负按回合，不按词数。**
Agent 一次可以猜 64 个词，但那只是「一个回合」——它代表一次思维决策。
按词数算的话，Agent 狂猜一次就能碾压。

**3. Agent 只能看自己的历史。**
早期的 `view_topk` 直接返回答案的邻居列表，等于递答案。
现在 `review` 只整理 Agent 自己猜过的词。

## 词表口径（可换）

| 项 | 取值 |
|---|---|
| 谜底总数 | **22,479**（二字 18,799 / 三字 3,167 / 四字 483） |
| 主源 | jieba `dict.txt`，词频 ≥ 200 |
| 副源 | webdict（22 万条），词频 ≥ 3000 |
| 词性 | 只硬排除人名/机构/数词/虚词，不做正向白名单 |
| 排除规则 | 方位后缀、虚词前缀、叠词、高频短语 + 人工豁免 |

```bash
python scripts/build_wordlist.py --min-freq 100 --dry-run   # 试别的档位
python scripts/build_wordlist.py                            # 写入
python scripts/build_embeddings.py                          # 重算向量（约 3 分钟）
python scripts/audit_pool.py                                # 复核常见词覆盖
```

换词表不需要改游戏逻辑。

## 技术栈

| 层 | 技术 |
|---|---|
| 语义引擎 | BGE `bge-base-zh-v1.5` int8 ONNX + onnxruntime（纯 CPU） |
| 后端 | FastAPI + SSE 事件流 |
| 前端 | React 19 + TypeScript + Vite + Tailwind v4 |
| Agent | OpenAI 兼容 tool calling，任意模型可换 |

运行时依赖只有 `fastapi / uvicorn / onnxruntime / tokenizers / numpy / httpx`。

## 文档

- [Agent 设计](./docs/agent-design.md) — 信息边界、回合口径、prompt 里每条策略的由来
- [引擎与相似度](./docs/engine.md) — 为什么不用词向量表、字形干扰怎么解、检索基准
- [词表构建](./data/wordlists/README.md) — 三个走过弯路的口径决策

## 测试

```bash
./.venv/bin/python tests/smoke.py           # 25 项，不调模型
./.venv/bin/python tests/retrieval_bench.py # 检索质量基准
./.venv/bin/python tests/agent_race.py      # 真实跑一局（需模型）
```

检索基准是判断「引擎能不能撑起游戏」的核心指标：

| 指标 | 结果 |
|---|---|
| 前 10 命中 | 45% |
| 前 50 命中 | 69% |
| 前 200 命中 | 90% |

## 数据来源与许可

| 源 | 许可 |
|---|---|
| [jieba](https://github.com/fxsjy/jieba) `dict.txt` | MIT |
| [webdict](https://github.com/ling0322/webdict) | CC BY-SA 3.0（部分源自 CC-CEDICT） |
| [BAAI/bge-base-zh-v1.5](https://huggingface.co/BAAI/bge-base-zh-v1.5) | MIT |
| [Xenova/bge-base-zh-v1.5](https://huggingface.co/Xenova/bge-base-zh-v1.5) | MIT（ONNX 量化版） |

本项目代码 MIT。

## 已知限制

- 单进程内存会话，重启丢对局（替换 `store.py` 的 `Store` 即可持久化）
- BGE 对 2 字词区分度有限，60%~70% 这一段接近噪声，所以界面优先显示名次
- 名次表按「排序分」算，池外词的近似名次是插入位置，不是精确排名
- 四字谜底只有 483 个，比二字稀疏得多
