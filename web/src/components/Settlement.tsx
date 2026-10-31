interface Props {
  target: string;
  winner: "human" | "agent" | "tie" | null;
  mode: "versus" | "challenge";
  humanGuesses: number;
  agentGuesses: number;
  humanSolved: boolean;
  agentSolved: boolean;
  onClose: () => void;
  onAgain: () => void;
}

/**
 * 结算卡。对局结束后浮在内容上方；答案在这里才第一次出现。
 *
 * 视觉上让「赢家的数字」做主角：大字号 + 渐变，另一方压暗。
 */
export function Settlement(props: Props) {
  const { target, winner, mode, humanGuesses, agentGuesses,
          humanSolved, agentSolved, onClose, onAgain } = props;

  const headline =
    mode === "challenge"
      ? agentSolved ? "Agent 解出来了" : "Agent 没猜出来"
      : winner === "human" ? "你赢了" : winner === "agent" ? "Agent 赢了" : "平局";

  const tone =
    mode === "challenge"
      ? agentSolved ? "rgb(var(--accent-2))" : "rgb(var(--fg-muted))"
      : winner === "human" ? "rgb(var(--exact))"
        : winner === "agent" ? "rgb(var(--accent-3))"
          : "rgb(var(--fg-muted))";

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-black/55 p-4 backdrop-blur-[2px]">
      <div className="glass glass-hi rise w-full max-w-md overflow-hidden"
           role="dialog" aria-modal="true" aria-label="对局结算">
        <div className="px-6 pt-7 text-center">
          <p className="text-[11px] uppercase tracking-[0.2em] text-[rgb(var(--fg-faint))]">
            本局答案
          </p>
          <p className="mt-2 text-4xl font-semibold tracking-[0.12em]">{target}</p>
          <p className="mt-4 text-xl font-semibold" style={{ color: tone }}>
            {headline}
          </p>
        </div>

        {mode === "versus" && (
          <div className="mt-6 grid grid-cols-2 divide-x divide-[rgb(var(--border))] border-y border-[rgb(var(--border))]">
            <Score label="你" value={humanGuesses} solved={humanSolved}
                   winner={winner === "human"} accent="rgb(var(--exact))" />
            <Score label="Agent" value={agentGuesses} solved={agentSolved}
                   winner={winner === "agent"} accent="rgb(var(--accent-3))" />
          </div>
        )}

        {mode === "challenge" && (
          <div className="mt-6 border-y border-[rgb(var(--border))] px-6 py-4">
            <div className="flex items-baseline justify-between text-sm">
              <span className="text-[rgb(var(--fg-muted))]">Agent 消耗回合</span>
              <span className="text-2xl font-semibold tabular-nums">{agentGuesses}</span>
            </div>
          </div>
        )}

        <div className="flex gap-2 p-5">
          <button className="btn btn-ghost flex-1" onClick={onClose}>看记录</button>
          <button className="btn btn-primary flex-1" onClick={onAgain}>再来一局</button>
        </div>
      </div>
    </div>
  );
}

function Score({ label, value, solved, winner, accent }: {
  label: string; value: number; solved: boolean; winner: boolean; accent: string;
}) {
  return (
    <div className={"px-5 py-4 text-center " + (winner ? "" : "opacity-45")}>
      <p className="text-[11px] text-[rgb(var(--fg-faint))]">{label}</p>
      <p className="mt-1 text-3xl font-semibold tabular-nums" style={{ color: accent }}>
        {solved ? value : "—"}
      </p>
      <p className="mt-0.5 text-[11px] text-[rgb(var(--fg-faint))]">
        {solved ? "回合猜中" : "未猜中"}
      </p>
    </div>
  );
}
