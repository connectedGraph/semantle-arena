import type { GuessRecord, Mode } from "../types";
import { ResultTable } from "./ResultTable";

interface Props {
  mode: Mode;
  rows: GuessRecord[];
  guesses: number;
  done: boolean;
  solved: boolean;
  running: boolean;
  targetLength: number;
  /* challenge 模式下的出题输入 */
  challengeOpen: boolean;
  onChallengeToggle: () => void;
  challengeTarget: string;
  onChallengeTarget: (v: string) => void;
  onChallengeStart: () => void;
  challengeError: string | null;
  onGuess: (word: string) => void;
  onGiveup: () => void;
  error: string | null;
  busy: boolean;
  disabled: boolean;
}

/**
 * 人类侧面板。
 *
 * 游戏进行中的主输入始终可用；「出题」在 challenge 模式下以抽屉形式展开，
 * 避免和猜词输入抢焦点。
 */
export function HumanPanel(props: Props) {
  const {
    mode, rows, guesses, done, solved, targetLength, challengeOpen,
    onChallengeToggle, challengeTarget, onChallengeTarget, onChallengeStart,
    challengeError, onGuess, onGiveup, error, busy, disabled,
  } = props;

  const placeholder =
    mode === "challenge" && !rows.length
      ? "先出一个题给 Agent 猜"
      : done
        ? "本局已结束"
        : "输入一个中文词，回车";

  return (
    <section className="glass glass-edge flex min-h-0 flex-col overflow-hidden">
      <header className="flex items-center justify-between gap-3 border-b border-[rgb(var(--border))] px-5 py-3.5">
        <div className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg bg-[rgb(var(--accent)/0.14)] text-sm font-semibold text-[rgb(var(--accent))]">
            你
          </span>
          <div className="leading-tight">
            <h2 className="text-sm font-semibold">你的猜测</h2>
            <p className="text-[11px] text-[rgb(var(--fg-faint))]">
              {guesses} 次 · 答案 {targetLength} 个字
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {solved && (
            <span className="level-exact level-chip rounded-full px-2.5 py-0.5 text-[11px] font-medium">
              已命中
            </span>
          )}
          {!done && !solved && (
            <button className="btn btn-ghost !px-2.5 !py-1 text-xs" onClick={onGiveup}
                    disabled={disabled}>
              放弃
            </button>
          )}
        </div>
      </header>

      {mode === "challenge" && (
        <div className="border-b border-[rgb(var(--border))] px-5 py-2.5">
          <button
            className="flex w-full items-center justify-between text-xs text-[rgb(var(--fg-muted))]"
            onClick={onChallengeToggle}
          >
            <span>出题给 Agent 猜（留空则随机）</span>
            <span className="text-[rgb(var(--fg-faint))]">{challengeOpen ? "收起" : "展开"}</span>
          </button>
          {challengeOpen && (
            <div className="rise mt-2 flex gap-2">
              <input
                className="field !py-1.5 text-sm"
                placeholder="输入 2~4 字作为答案"
                value={challengeTarget}
                maxLength={8}
                onChange={(e) => onChallengeTarget(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && onChallengeStart()}
              />
              <button className="btn btn-primary shrink-0 !py-1.5 text-sm"
                      onClick={onChallengeStart}>
                开局
              </button>
            </div>
          )}
          {challengeError && (
            <p className="mt-1.5 text-[11px] text-rose-400">{challengeError}</p>
          )}
        </div>
      )}

      <ResultTable rows={rows} side="human" className="px-3 py-2" />

      <footer className="border-t border-[rgb(var(--border))] p-3">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const input = (e.currentTarget.elements.namedItem("w") as HTMLInputElement);
            const v = input.value.trim();
            if (v) {
              onGuess(v);
              input.value = "";
            }
          }}
        >
          <input
            name="w"
            className="field"
            placeholder={placeholder}
            disabled={disabled || done || mode === "challenge"}
            autoComplete="off"
            autoFocus
          />
          <button
            type="submit"
            className="btn btn-primary shrink-0 px-4"
            disabled={disabled || done || mode === "challenge"}
          >
            {busy ? "…" : "猜"}
          </button>
        </form>
        {error && <p className="mt-2 text-xs text-rose-400">{error}</p>}
      </footer>
    </section>
  );
}
