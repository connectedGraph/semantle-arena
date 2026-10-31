import type { Meta } from "../types";

interface Props {
  meta: Meta | null;
  onStart: () => void;
  mode: "versus" | "challenge";
}

/**
 * 开场屏。对局未开始时占据主区域。
 *
 * 目的不是「装饰」，而是把三件事说清楚：
 * 1. 这是一场什么比赛（人 vs Agent，比谁的回合少）
 * 2. Agent 凭什么合理（只有两个工具，看不到答案）
 * 3. 词表有多可信（真实数字，不是宣传语）
 */
export function Hero({ meta, onStart, mode }: Props) {
  const count = meta?.pool.count;
  const two = meta?.pool.by_length?.["2"];
  const three = meta?.pool.by_length?.["3"];

  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-6 py-10">
      <div className="w-full max-w-3xl">
        <p className="text-center text-[11px] uppercase tracking-[0.32em] text-[rgb(var(--accent-2))]">
          Human vs Agent
        </p>

        <h2 className="mt-4 text-center text-[clamp(2rem,4.2vw,3.4rem)] font-semibold leading-[1.1] tracking-tight">
          <span className="text-gradient">同一个隐藏词</span>
          <br />
          <span className="text-[rgb(var(--fg))]">看谁先猜中，且更少回合</span>
        </h2>

        <p className="mx-auto mt-5 max-w-xl text-center text-sm leading-relaxed text-[rgb(var(--fg-muted))]">
          你和 Agent 拿到同一个中文词。每次猜词会返回它和答案的语义相似度与名次。
          Agent<span className="text-[rgb(var(--fg))]">看不到答案</span>，
          只能靠 <code className="rounded bg-[rgb(var(--fg)/0.08)] px-1.5 py-0.5 font-mono text-[12px]">guess</code>
          {" "}试探和 <code className="rounded bg-[rgb(var(--fg)/0.08)] px-1.5 py-0.5 font-mono text-[12px]">review</code>
          {" "}回顾自己的战绩。
        </p>

        <div className="mt-9 grid gap-3 sm:grid-cols-3">
          <Stat value={count ? count.toLocaleString() : "—"} label="当前词库" sub={
            meta?.pool.tier === "small" ? "精简档 · 日常具象词"
              : meta?.pool.tier === "medium" ? "标准档"
                : "完整档"
          } />
          <Stat value={two ? two.toLocaleString() : "—"} label="二字谜底" sub="主力玩法" />
          <Stat value={three ? three.toLocaleString() : "—"} label="三字谜底" sub="更长也更好玩" />
        </div>

        <div className="mt-8 flex flex-col items-center gap-3">
          <button className="btn btn-primary !px-7 !py-3 text-[15px]" onClick={onStart}>
            {mode === "versus" ? "开始人机对战" : "开始出题"}
          </button>
          <p className="text-[11px] text-[rgb(var(--fg-faint))]">
            谜底受限，猜词不限——词池里没有的词也照常算相似度
          </p>
        </div>
      </div>
    </div>
  );
}

function Stat({ value, label, sub }: { value: string; label: string; sub: string }) {
  return (
    <div className="glass px-4 py-3.5 text-center">
      <p className="font-mono text-2xl font-semibold tabular-nums text-[rgb(var(--fg))]">
        {value}
      </p>
      <p className="mt-0.5 text-xs text-[rgb(var(--fg-muted))]">{label}</p>
      <p className="text-[10px] text-[rgb(var(--fg-faint))]">{sub}</p>
    </div>
  );
}
