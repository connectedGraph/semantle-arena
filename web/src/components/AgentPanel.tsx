import type { GuessRecord, LogEntry } from "../types";
import { ResultTable } from "./ResultTable";

interface Props {
  rows: GuessRecord[];
  guesses: number;
  step: number;
  maxSteps: number;
  solved: boolean;
  done: boolean;
  logs: LogEntry[];
  masked: boolean;
  onToggleMask: () => void;
  running: boolean;
}

/**
 * Agent 侧面板。
 *
 * 思考过程与结果默认在同屏展示；对局中可选「遮蔽」，把对方猜词藏起来，
 * 让比赛不被抄答案。遮蔽只在有跑动时才有意义，所以按钮跟着状态走。
 */
export function AgentPanel(props: Props) {
  const { rows, guesses, step, maxSteps, solved, done, logs, masked,
          onToggleMask, running } = props;

  const progress = maxSteps > 0 ? Math.min(100, (step / maxSteps) * 100) : 0;

  return (
    <section className="glass flex min-h-0 flex-col overflow-hidden">
      <header className="border-b border-[rgb(var(--border))] px-5 py-3.5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span
              className={
                "relative grid size-8 place-items-center rounded-lg text-sm font-semibold " +
                (running
                  ? "bg-[rgb(var(--accent-2)/0.16)] text-[rgb(var(--accent-2))]"
                  : "bg-[rgb(var(--fg)/0.06)] text-[rgb(var(--fg-muted))]")
              }
            >
              AI
              {running && (
                <span className="pulse-dot absolute -right-0.5 -top-0.5 size-2 rounded-full bg-[rgb(var(--accent-2))]" />
              )}
            </span>
            <div className="leading-tight">
              <h2 className="text-sm font-semibold">Agent 的猜测</h2>
              <p className="text-[11px] text-[rgb(var(--fg-faint))]">
                {guesses} 次 · 第 {step}/{maxSteps} 步
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {solved && (
              <span className="level-exact level-chip rounded-full px-2.5 py-0.5 text-[11px] font-medium">
                已命中
              </span>
            )}
            {done && !solved && (
              <span className="rounded-full border border-[rgb(var(--border))] px-2.5 py-0.5 text-[11px] text-[rgb(var(--fg-faint))]">
                未猜中
              </span>
            )}
            <button
              className="btn btn-ghost !px-2.5 !py-1 text-xs"
              onClick={onToggleMask}
              aria-pressed={masked}
            >
              {masked ? "显示" : "遮蔽"}
            </button>
          </div>
        </div>

        <div className="mt-2.5 h-1 overflow-hidden rounded-full bg-[rgb(var(--fg)/0.08)]">
          <div
            className="h-full rounded-full bg-gradient-to-r from-[rgb(var(--accent))] to-[rgb(var(--accent-2))] transition-[width] duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-rows-[1fr_auto]">
        <ResultTable rows={rows} side="agent" masked={masked} className="px-3 py-2" />
        <AgentLog logs={logs} masked={masked && !done} done={done} />
      </div>
    </section>
  );
}

function AgentLog({ logs, masked, done }: { logs: LogEntry[]; masked: boolean; done: boolean }) {
  const shown = logs.slice(-40);
  return (
    <div className="border-t border-[rgb(var(--border))] px-4 py-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest text-[rgb(var(--fg-faint))]">
          推理轨迹
        </span>
        <span className="text-[10px] text-[rgb(var(--fg-faint))]">
          {masked ? "已遮蔽 · 结束后揭晓" : `${logs.length} 条`}
        </span>
      </div>
      <div className="scroll-thin h-32 space-y-1 overflow-y-auto font-mono text-[11px] leading-relaxed">
        {logs.length === 0 && (
          <p className="text-[rgb(var(--fg-faint))]">
            {done
              ? "本局已结束。推理轨迹只在对局进行时实时推送，刷新页面后不再回放。"
              : "等待 Agent 启动…"}
          </p>
        )}
        {shown.map((l) => (
          <div key={l.id} className="flex gap-1.5">
            <span className={badgeClass(l.kind)}>{badgeLabel(l.kind)}</span>
            <span className="min-w-0 flex-1 break-words text-[rgb(var(--fg-muted))]">
              {masked && l.kind === "result" ? "…" : l.text}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function badgeLabel(kind: LogEntry["kind"]): string {
  return { assistant: "说", call: "调", result: "果", step: "步", error: "错" }[kind];
}

function badgeClass(kind: LogEntry["kind"]): string {
  const base = "shrink-0 rounded px-1 text-[10px] font-semibold";
  switch (kind) {
    case "call":
      return `${base} bg-[rgb(var(--accent)/0.18)] text-[rgb(var(--accent))]`;
    case "result":
      return `${base} bg-[rgb(var(--accent-2)/0.15)] text-[rgb(var(--accent-2))]`;
    case "error":
      return `${base} bg-rose-500/15 text-rose-400`;
    default:
      return `${base} bg-[rgb(var(--fg)/0.08)] text-[rgb(var(--fg-faint))]`;
  }
}
