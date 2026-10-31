import { useEffect, useRef, useState } from "react";

interface Props {
  started: boolean;
  target: string | null;
  busy: boolean;
  onChallenge: (target: string) => void;
}

const CJK = /^[一-鿿]{1,8}$/;

/**
 * 出题模式的输入条。
 *
 * 出题模式下人类没有棋盘可看，所以不占一整栏——一条窄条放在顶部，
 * 剩下的宽度全给 Agent，否则左边是一大片空白。
 */
export function ChallengeBar({ started, target, busy, onChallenge }: Props) {
  const [draft, setDraft] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setDraft("");
    setErr(null);
    ref.current?.focus();
  }, [target]);

  const submit = () => {
    const w = draft.trim();
    if (w && !CJK.test(w)) {
      setErr("只能输入 1~8 个汉字");
      return;
    }
    setErr(null);
    onChallenge(w);       // 留空 = 词库随机出题
  };

  return (
    <div className="glass glass-edge flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
      <div className="flex items-baseline gap-2">
        <span className="text-[11px] text-[rgb(var(--fg-faint))]">出题</span>
        <span className="text-xs text-[rgb(var(--fg-muted))]">
          {started && target
            ? <>谜底 <span className="text-base font-semibold tracking-[0.12em] text-[rgb(var(--fg))]">{target}</span></>
            : "填一个词让 Agent 猜"}
        </span>
      </div>

      <form
        className="flex min-w-0 flex-1 gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <input
          ref={ref}
          className="field !w-auto min-w-0 flex-1 !py-1.5"
          placeholder="谜底，留空则随机"
          value={draft}
          maxLength={8}
          autoComplete="off"
          onChange={(e) => {
            setErr(null);
            setDraft(e.target.value);
          }}
        />
        <button type="submit" className="btn btn-primary shrink-0 !py-1.5" disabled={busy}>
          {busy ? "…" : started ? "换一道" : "开局"}
        </button>
      </form>

      {err && <p className="w-full text-xs text-rose-400">{err}</p>}
    </div>
  );
}
