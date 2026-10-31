import type { GuessRecord } from "../types";

/**
 * 色条宽度按**名次**编码，而不是相似度。
 *
 * 原因：列表按名次排序，而名次与相似度并非严格同序（字符重叠惩罚会调整顺序，
 * 例如「小提琴 80.18% rank 6」排在「音乐 76.60% rank 1」后面）。
 * 若色条画相似度，读者会看到「更长的条排在更下面」而困惑。
 * 让色条与排序同源，视觉才自洽；相似度仍以数字给出。
 */
function rankBarWidth(rank: number | null): number {
  if (rank === null) return 4;                 // 3000+ 之外：给一条最短可见
  if (rank === 1) return 100;
  // 对数刻度：1 -> 100%，10 -> ~75%，100 -> ~50%，1000 -> ~25%
  const w = 100 - (Math.log10(rank) / Math.log10(3200)) * 82;
  return Math.max(4, Math.min(100, w));
}

interface Props {
  rows: GuessRecord[];
  /** 面板归属，只影响空态文案 */
  side: "human" | "agent";
  /** 是否遮蔽（对局中隐藏 Agent 结果） */
  masked?: boolean;
  className?: string;
}

/**
 * 猜词结果表。
 * 排序固定：名次升序（无名词次排最后），同名次按相似度降序。
 * 每行一条接近度色条，长度按相似度比例映射，冷词给一个最小可见宽度。
 */
export function ResultTable({ rows, side, masked, className }: Props) {
  const sorted = [...rows].sort((a, b) => {
    const ra = a.rank ?? 1e9;
    const rb = b.rank ?? 1e9;
    if (ra !== rb) return ra - rb;
    return b.similarity - a.similarity;
  });

  if (!sorted.length) {
    return (
      <div
        className={
          "flex flex-1 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-[rgb(var(--border))] px-6 py-10 text-center " +
          (className ?? "")
        }
      >
        <div className="text-2xl opacity-25">◌</div>
        <p className="text-sm text-[rgb(var(--fg-muted))]">
          {side === "human" ? "还没有猜词" : "等待 Agent 第一次试探"}
        </p>
        <p className="text-xs text-[rgb(var(--fg-faint))]">
          {side === "human" ? "输入任意中文表达，看它与答案有多接近" : "Agent 的每一步都会实时出现在这里"}
        </p>
      </div>
    );
  }

  return (
    <div className={"scroll-thin flex-1 overflow-y-auto pr-1 " + (className ?? "")}>
      <table className="w-full border-separate border-spacing-y-1 text-sm">
        <thead className="sticky top-0 z-10 bg-[rgb(var(--bg-veil))]/80 backdrop-blur-sm">
          <tr className="text-[11px] uppercase tracking-wider text-[rgb(var(--fg-faint))]">
            <th className="w-9 pb-1 text-left font-medium">序</th>
            <th className="pb-1 text-left font-medium">词</th>
            <th className="w-16 pb-1 text-right font-medium">名次</th>
            <th className="w-20 pb-1 text-right font-medium">相似度</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => {
            const pct = rankBarWidth(r.rank);
            const hidden = Boolean(masked) && !r.is_target;
            return (
              <tr
                key={r.word}
                className={`level-${r.level} group rise`}
                style={{ animationDelay: `${Math.min(i, 12) * 18}ms` }}
              >
                <td className="rounded-l-lg bg-[rgb(var(--fg)/0.03)] px-2 py-1.5 text-xs tabular-nums text-[rgb(var(--fg-faint))]">
                  {i + 1}
                </td>
                <td className="relative bg-[rgb(var(--fg)/0.03)] px-2 py-1.5">
                  <div
                    aria-hidden
                    className="level-bar absolute inset-y-1 left-0 rounded-md opacity-[0.16] transition-[width] duration-500"
                    style={{ width: `${pct}%` }}
                  />
                  <span className="relative font-medium tracking-wide">
                    {hidden ? "•••" : r.word}
                  </span>
                  {r.is_target && <span className="ml-2 text-xs level-text">命中</span>}
                  {r.approx && !hidden && (
                    <span
                      className="ml-2 rounded px-1 py-0.5 text-[10px] text-[rgb(var(--fg-faint))] ring-1 ring-[rgb(var(--border))]"
                      title="这个词不在词库里，分数由汉字向量平均估算，仅供参考"
                    >
                      估算
                    </span>
                  )}
                </td>
                <td className="bg-[rgb(var(--fg)/0.03)] px-2 py-1.5 text-right">
                  <RankChip rank={r.rank} hidden={hidden} />
                </td>
                <td className="rounded-r-lg bg-[rgb(var(--fg)/0.03)] px-2 py-1.5 text-right">
                  <span className="tabular-nums level-text">
                    {hidden ? "-" : r.similarity_pct.toFixed(2)}
                    <span className="text-[10px] opacity-60">%</span>
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RankChip({ rank, hidden }: { rank: number | null; hidden: boolean }) {
  if (hidden) return <span className="text-xs text-[rgb(var(--fg-faint))]">-</span>;
  if (rank === null) {
    return (
      <span className="rounded-md border border-[rgb(var(--border))] px-1.5 py-0.5 text-[11px] text-[rgb(var(--fg-faint))]">
        3000+
      </span>
    );
  }
  return (
    <span className="tabular-nums text-xs text-[rgb(var(--fg-muted))]">
      {rank === 1 ? "1" : rank.toLocaleString()}
    </span>
  );
}
