import { useEffect, useRef, useState } from "react";
import type { GuessRecord } from "../types";
import { ResultTable } from "./ResultTable";

interface Props {
  rows: GuessRecord[];
  words: number;
  done: boolean;
  solved: boolean;
  started: boolean;
  targetLength: number;
  onGuess: (word: string) => void;
  onGiveup: () => void;
  busy: boolean;
}

const CJK = /^[一-鿿]{1,8}$/;

/**
 * 人机对战里人类一侧：结果表 + 输入框。
 *
 * 输入第一个词就自动开局（见 App 的 onGuess → useRace.guess），
 * 所以没有「开始」按钮——点了开局，光标本来也在这里。
 */
export function HumanPanel(props: Props) {
  const { rows, words, done, solved, started, targetLength, onGuess, onGiveup, busy } = props;

  const inputRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const locked = done || solved;

  useEffect(() => {
    if (!locked) inputRef.current?.focus();
  }, [locked, started]);

  const submit = () => {
    const w = draft.trim();
    if (!w) return;
    if (!CJK.test(w)) {
      setErr("只能输入 1~8 个汉字");
      return;
    }
    setErr(null);
    setDraft("");
    onGuess(w);
  };

  return (
    <section className="glass glass-edge flex min-h-0 flex-col overflow-hidden">
      <header className="flex items-center justify-between gap-3 border-b border-[rgb(var(--border))] px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="grid size-7 place-items-center rounded-lg bg-[rgb(var(--accent)/0.14)] text-xs font-semibold text-[rgb(var(--accent))]">
            你
          </span>
          <div className="leading-tight">
            <h2 className="text-sm font-semibold">你的猜测</h2>
            <p className="text-[11px] tabular-nums text-[rgb(var(--fg-faint))]">
              {words} 词 · 答案 {targetLength} 个字
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {solved && (
            <span className="level-exact level-chip rounded-full px-2.5 py-0.5 text-[11px] font-medium">
              命中
            </span>
          )}
          {!locked && started && (
            <button className="btn btn-ghost !px-2.5 !py-1 text-xs" onClick={onGiveup}>
              放弃
            </button>
          )}
        </div>
      </header>

      <ResultTable rows={rows} side="human" className="px-2 py-2" />

      <footer className="border-t border-[rgb(var(--border))] p-2.5">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <input
            ref={inputRef}
            className="field"
            placeholder={solved ? "已猜中" : done ? "本局已结束" : "输入一个词，回车开局"}
            value={draft}
            disabled={locked}
            autoComplete="off"
            autoFocus
            onChange={(e) => {
              setErr(null);
              setDraft(e.target.value);
            }}
          />
          <button type="submit" className="btn btn-primary shrink-0 px-4" disabled={locked}>
            {busy ? "…" : "猜"}
          </button>
        </form>
        {err && <p className="mt-1.5 text-xs text-rose-400">{err}</p>}
      </footer>
    </section>
  );
}
