import type { Mode } from "../types";

interface Props {
  target: string;
  winner: "human" | "agent" | "tie" | null;
  mode: Mode;
  humanWords: number;
  agentWords: number;
  humanSolved: boolean;
  agentSolved: boolean;
  onAgain: () => void;
}

/**
 * 结算条。**内联在棋盘上方，不做成弹窗**。
 *
 * 弹出的对话框会盖住结果表——而那正是玩家最想看的东西（Agent 到底猜了哪些词）。
 * 内联一条横幅：答案、胜负、词数对比，剩下的空间留给下面的两张表。
 */
export function RoundResult(props: Props) {
  const { target, winner, mode, humanWords, agentWords,
          humanSolved, agentSolved, onAgain } = props;

  const headline =
    mode === "challenge"
      ? agentSolved ? "Agent 解出来了" : "Agent 没猜出来"
      : winner === "human" ? "你赢了"
        : winner === "agent" ? "Agent 赢了"
          : "平局";

  const tone =
    mode === "challenge"
      ? agentSolved ? "rgb(var(--accent-2))" : "rgb(var(--fg-muted))"
      : winner === "human" ? "rgb(var(--exact))"
        : winner === "agent" ? "rgb(var(--accent-3))"
          : "rgb(var(--fg-muted))";

  return (
    <div className="rise glass glass-edge mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2.5">
      <div className="flex items-baseline gap-2">
        <span className="text-[11px] text-[rgb(var(--fg-faint))]">答案</span>
        <span className="text-xl font-semibold tracking-[0.13em]">{target}</span>
      </div>

      <span className="text-base font-semibold" style={{ color: tone }}>
        {headline}
      </span>

      {mode === "versus" && (
        <div className="flex items-center gap-4 text-xs">
          <Score label="你" words={humanWords} solved={humanSolved}
                 winner={winner === "human"} accent="rgb(var(--exact))" />
          <Score label="Agent" words={agentWords} solved={agentSolved}
                 winner={winner === "agent"} accent="rgb(var(--accent-3))" />
        </div>
      )}

      {mode === "challenge" && (
        <span className="text-xs text-[rgb(var(--fg-muted))]">
          Agent 用掉 <span className="tabular-nums text-[rgb(var(--fg))]">{agentWords}</span> 个词
        </span>
      )}

      <button className="btn btn-primary ml-auto !py-1.5" onClick={onAgain}>
        再来一局
      </button>
    </div>
  );
}

function Score({ label, words, solved, winner, accent }: {
  label: string; words: number; solved: boolean; winner: boolean; accent: string;
}) {
  return (
    <span className={"flex items-baseline gap-1.5 " + (winner ? "" : "opacity-45")}>
      <span className="text-[rgb(var(--fg-faint))]">{label}</span>
      <span className="tabular-nums text-lg font-semibold" style={{ color: accent }}>
        {solved ? words : "—"}
      </span>
      <span className="text-[rgb(var(--fg-faint))]">词</span>
    </span>
  );
}
