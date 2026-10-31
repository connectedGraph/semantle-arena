import type { GuessRecord, LogEntry } from "../types";
import { ResultTable } from "./ResultTable";

interface Props {
  rows: GuessRecord[];
  words: number;
  step: number;
  maxSteps: number;
  solved: boolean;
  done: boolean;
  logs: LogEntry[];
  /** 是否公开 Agent 的猜测与推理 */
  revealed: boolean;
  running: boolean;
  started: boolean;
  onReveal: () => void;
}

/**
 * Agent 侧面板。
 *
 * 默认**隐藏**猜测内容和推理轨迹。这不是「可选项」而是默认值：
 * 对局中看着对手的答案猜，比较本身就失去意义了。
 * 结算后 `race_end` 会自动揭晓；局中想偷看可以点「揭晓」，代价自负。
 */
export function AgentPanel(props: Props) {
  const { rows, words, step, maxSteps, solved, done, logs, revealed,
          running, started, onReveal } = props;

  const progress = maxSteps > 0 ? Math.min(100, (step / maxSteps) * 100) : 0;
  const visible = revealed;

  return (
    <section className="glass flex min-h-0 flex-col overflow-hidden">
      <header className="border-b border-[rgb(var(--border))] px-4 py-2.5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span
              className={
                "relative grid size-7 place-items-center rounded-lg text-[11px] font-semibold " +
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
              <h2 className="text-sm font-semibold">Agent</h2>
              <p className="text-[11px] tabular-nums text-[rgb(var(--fg-faint))]">
                {/* 步数只在实时推送时才有；刷新恢复的对局没有，就不显示「第 0 步」 */}
                {visible
                  ? `${words} 词` + (step > 0 ? ` · 第 ${step}/${maxSteps} 步` : "")
                  : done ? "已停止"
                    : running ? `进行中 · 第 ${step}/${maxSteps} 步` : "未开始"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* 命中与词数在揭晓前都不能露：露出来等于告诉玩家「它已经赢了」。 */}
            {visible && solved && (
              <span className="level-exact level-chip rounded-full px-2.5 py-0.5 text-[11px] font-medium">
                命中
              </span>
            )}
            {visible && done && !solved && (
              <span className="rounded-full border border-[rgb(var(--border))] px-2.5 py-0.5 text-[11px] text-[rgb(var(--fg-faint))]">
                未猜中
              </span>
            )}
            {!visible && started && (
              <button className="btn btn-ghost !px-2.5 !py-1 text-xs" onClick={onReveal}
                      title="提前查看对手的猜测，比较就没意义了">
                揭晓
              </button>
            )}
          </div>
        </div>

        <div className="mt-2 h-1 overflow-hidden rounded-full bg-[rgb(var(--fg)/0.08)]">
          <div
            className="h-full rounded-full bg-gradient-to-r from-[rgb(var(--accent))] to-[rgb(var(--accent-2))] transition-[width] duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </header>

      {visible ? (
        <div className="grid min-h-0 flex-1 grid-rows-[1fr_auto]">
          <ResultTable rows={rows} side="agent" className="px-2 py-2" />
          <AgentLog logs={logs} done={done} />
        </div>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
          <div className="text-3xl opacity-20">◍</div>
          <p className="text-sm text-[rgb(var(--fg-muted))]">
            {done ? "Agent 已结束，结算时揭晓"
              : started ? "Agent 正在猜，内容已隐藏" : "Agent 待命中"}
          </p>
          <p className="max-w-[22rem] text-[11px] leading-relaxed text-[rgb(var(--fg-faint))]">
            {started
              ? "它的猜测与推理在结算时揭晓。现在就看不影响你猜，但会影响这场比较的可信度。"
              : "你输入第一个词，或出一个题，它就开局。"}
          </p>
        </div>
      )}
    </section>
  );
}

function AgentLog({ logs, done }: { logs: LogEntry[]; done: boolean }) {
  const shown = logs.slice(-40);
  return (
    <div className="border-t border-[rgb(var(--border))] px-3 py-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest text-[rgb(var(--fg-faint))]">
          推理轨迹
        </span>
        <span className="text-[10px] text-[rgb(var(--fg-faint))]">{logs.length} 条</span>
      </div>
      <div className="scroll-thin h-28 space-y-1 overflow-y-auto font-mono text-[11px] leading-relaxed">
        {logs.length === 0 && (
          <p className="text-[rgb(var(--fg-faint))]">
            {done ? "本局已结束。轨迹只在开局后实时推送。" : "等待 Agent 启动…"}
          </p>
        )}
        {shown.map((l) => (
          <div key={l.id} className="flex gap-1.5">
            <span className={badgeClass(l.kind)}>{badgeLabel(l.kind)}</span>
            <span className="min-w-0 flex-1 break-words text-[rgb(var(--fg-muted))]">
              {l.text}
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
