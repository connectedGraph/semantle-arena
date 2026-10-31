import { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { HumanPanel } from "./components/HumanPanel";
import { AgentPanel } from "./components/AgentPanel";
import { Settlement } from "./components/Settlement";
import { PoolSheet } from "./components/PoolSheet";
import { Hero } from "./components/Hero";
import { useRace } from "./hooks/useRace";
import { useTheme } from "./hooks/useTheme";
import { getMeta } from "./lib/api";
import type { Meta, Mode } from "./types";

export default function App() {
  const { theme, toggle } = useTheme();
  const { state, begin, restore, guess, giveup, toggleAgent, clearError } = useRace();

  const [mode, setMode] = useState<Mode>("versus");
  const [length, setLength] = useState(2);
  const [maxSteps, setMaxSteps] = useState(30);
  const [challengeOpen, setChallengeOpen] = useState(false);
  const [challengeTarget, setChallengeTarget] = useState("");
  const [challengeError, setChallengeError] = useState<string | null>(null);
  const [poolOpen, setPoolOpen] = useState(false);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [settlementDismissed, setSettlementDismissed] = useState(false);

  useEffect(() => {
    getMeta().then(setMeta).catch(() => undefined);
  }, []);

  // ?race=<id> 恢复一局（对局可分享/可刷新不丢）
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("race");
    if (id) {
      setSettlementDismissed(true);   // 刷新/分享恢复时不挡住结果表
      void restore(id);
    }
  }, [restore]);

  const locked = state.phase === "running";

  const startNew = async () => {
    setSettlementDismissed(false);
    await begin(mode, maxSteps, { minLen: length, maxLen: length });
  };

  const startChallenge = async () => {
    const t = challengeTarget.trim();
    if (t && !/^[一-鿿]{1,8}$/.test(t)) {
      setChallengeError("只能输入 1~8 个汉字");
      return;
    }
    setChallengeError(null);
    setSettlementDismissed(false);
    await begin("challenge", maxSteps, { targetWord: t || undefined });
  };

  const showSettlement =
    state.phase === "finished" && !!state.target && !settlementDismissed;

  return (
    <>
      <div className="arena-backdrop" />

      <Header
        mode={mode}
        onModeChange={(m) => {
          setMode(m);
          setChallengeOpen(m === "challenge");
        }}
        length={length}
        onLengthChange={setLength}
        maxSteps={maxSteps}
        onMaxStepsChange={setMaxSteps}
        onNew={startNew}
        onToggleTheme={toggle}
        dark={theme === "dark"}
        meta={meta}
        locked={locked}
        phase={state.phase}
      />

      <main className="mx-auto w-full max-w-[1400px] px-5 pb-5">
        {state.error && (
          <div className="mt-3 flex items-start justify-between gap-3 rounded-xl border border-rose-500/35 bg-rose-500/10 px-4 py-2.5 text-sm text-rose-300">
            <span>{state.error}</span>
            <button className="text-xs underline opacity-70" onClick={clearError}>关闭</button>
          </div>
        )}

        {state.phase === "idle" ? (
          <div className="flex flex-col" style={{ minHeight: "calc(100dvh - 9rem)" }}>
            <Hero meta={meta} onStart={startNew} mode={mode} />
          </div>
        ) : (
        <div className="grid gap-4 pt-4 lg:grid-cols-2 lg:items-stretch"
             style={{ minHeight: "calc(100dvh - 11rem)" }}>
          <HumanPanel
            mode={mode}
            rows={Object.values(state.human)}
            guesses={Object.keys(state.human).length}
            done={state.humanDone}
            solved={state.humanSolved}
            running={state.phase === "running"}
            targetLength={state.targetLength || length}
            challengeOpen={challengeOpen}
            onChallengeToggle={() => setChallengeOpen((v) => !v)}
            challengeTarget={challengeTarget}
            onChallengeTarget={setChallengeTarget}
            onChallengeStart={startChallenge}
            challengeError={challengeError}
            onGuess={guess}
            onGiveup={giveup}
            error={null}
            busy={state.busy}
            disabled={false}
          />

          <AgentPanel
            rows={Object.values(state.agent)}
            guesses={Object.keys(state.agent).length}
            step={state.step}
            maxSteps={state.maxSteps || maxSteps}
            solved={state.agentSolved}
            done={state.agentDone}
            logs={state.logs}
            masked={!state.showAgent}
            onToggleMask={toggleAgent}
            running={state.phase === "running"}
          />
        </div>
        )}

        <footer className="mt-4 flex flex-wrap items-center justify-between gap-2 text-[11px] text-[rgb(var(--fg-faint))]">
          <span>
            {state.phase === "idle"
              ? "点右上「开始对局」，你和 Agent 会拿到同一个隐藏词，比谁的猜测次数少。"
              : state.phase === "running"
                ? "对局进行中：左边随便猜，右边 Agent 会逐步试探。"
                : "本局已结算，可以「新开一局」或查看上面的结果表。"}
          </span>
          <button className="underline decoration-dotted hover:text-[rgb(var(--fg-muted))]"
                  onClick={() => setPoolOpen(true)}>
            词池与引擎说明
          </button>
        </footer>
      </main>

      <PoolSheet meta={meta} hidden={poolOpen} onClose={() => setPoolOpen(false)} />

      {showSettlement && state.target && (
        <Settlement
          target={state.target}
          winner={state.winner}
          mode={state.mode}
          humanGuesses={state.humanTurns || Object.keys(state.human).length}
          agentGuesses={state.agentTurns || Object.keys(state.agent).length}
          humanSolved={state.humanSolved}
          agentSolved={state.agentSolved}
          onClose={() => setSettlementDismissed(true)}
          onAgain={startNew}
        />
      )}
    </>
  );
}
