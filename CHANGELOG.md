# 变更记录

## 2026-10-31 · 首次发布

### 为什么重写

上一版 `chinese-semantle-agent` 是 fork 自 `ispacekid/chinese-semantle`，
自己加了 Agent 对战，但数据层是上游的，有两处硬伤：

1. **词表随意**：1897 个人工堆的具象名词，「风」系 19 个词同池，
   抽中「风韵」时同簇全是高相似度，难度被词表污染；
   且有 `航空母舰 / 核潜艇` 这类涉军词，与它自己的 blacklist 原则矛盾。
2. **词向量覆盖不全**：腾讯词向量 14.3 万词，`披萨 / 长颈鹿 / 贝多芬 / 躺平 / 社畜`
   都不在，猜这些词直接报错。

这两条都不是 Agent 层能修的，所以从零重写。

### 词表

- jieba + webdict 双源编译，17751 词（二字 15090 / 三字 2338 / 四字 323）
- 词性按品类分配门槛：名词类 200，动词/形容词 400（高频情绪词保留），副词不收
- webdict 只补 `n / nz`（它的高频区全是新闻词）
- `exclude.rules` 可配置规则 + `allow:` 人工豁免
- `scripts/audit_pool.py` 复核常见词覆盖

经历了 5 轮口径返工，详见 `data/wordlists/README.md`。

### 语义引擎

- bge-base-zh-v1.5 int8 ONNX，纯 CPU，无需 torch / GPU
- 字符重叠惩罚 0.15，解决 BGE 的字形干扰（钢琴→钢材、冰箱→木箱、大夫→姐夫）
- 检索基准：相关词前 200 命中 78%（在池词 90%）、前 50 命中 65%

### 玩法

- 谜底受限、猜词不限（池外词实时编码）
- 胜负按回合不按词数：Agent 一次 64 词仍算一回合
- Agent 只有 `guess` / `review` 两个工具，看不到答案
  （早期版本的 `view_topk` 会直接返回答案邻居，已废弃）

### 前端

- React 19 + TS + Vite + Tailwind v4
- 暗色玻璃拟态 + 极光渐变，默认深色（浅色可切）
- 接近度色条按**名次**编码而非相似度——保证与列表排序同源，不会出现
  「更长的条排在更下面」的矛盾
- SSE 实时推送 Agent 的思考、工具调用与结果

### 修复的 bug

- `human_guess` / `human_giveup` 是同步端点，跑在线程池里没有事件循环，
  `asyncio.create_task` 抛 `no running event loop` 直接打挂请求。
  改成线程安全的 `queue.Queue` + `emit_nowait`。
- 名次表把答案自己算作 rank 1，导致所有猜词名次整体后移一位、
  「最接近的词」永远显示 rank 2。
- `tokenizers` 批量编码必须开 padding，否则长短不一的词无法堆成矩阵。
- onnxruntime 线程数设成核数会超额订阅，比 2 线程还慢一倍。
