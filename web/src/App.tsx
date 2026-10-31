import { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { HumanPanel } from "./components/HumanPanel";
import { AgentPanel } from "./components/AgentPanel";
import { RoundResult } from "./components/RoundResult";
import { ChallengeBar } from "./components/ChallengeBar";
import { PoolSheet } from "./components/PoolSheet";
import { useRace } from "./hooks/useRace";
import { useTheme } from "./hooks/useTheme";
import { getMeta, setTier } from "./lib/api";
import type { Meta, Mode, Tier } from "./types";

const LENGTH_KEY = "arena-length";
const STEPS_KEY = "arena-steps";

function readNum(key: string, allowed: number[], fallback: number): number {
  const n = Number(localStorage.getItem(key));
  return allowed.includes(n) ? n : fallback;
}

/**
 * 单页布局，没有独立开场页。
 *
 * 交互约定（都是这一版改的）：
 * 1. 进来就是棋盘。人机对战直接输第一个词即开局，不用先点「开始」。
 * 2. 顶部任何设置对局中都能改——改了就是换一局，不锁控件。
 * 3. Agent 的猜测与推理默认隐藏，结算时才揭晓；想提前看可以手动「揭晓」。
 * 4. 胜负按猜中时用掉的词数比，不比时间。
 */
export default function App() {
  const { theme, toggle } = useTheme();
  const { state, begin, restore, guess, giveup, setReveal, reset, clearError } = useRace();

  const [mode, setMode] = useState<Mode>("versus");
  const [length, setLength] = useState(() => readNum(LENGTH_KEY, [2, 3, 4], 2));
  const [maxSteps, setMaxSteps] = useState(() => readNum(STEPS_KEY, [12, 30, 50], 30));
  const [poolOpen, setPoolOpen] = useState(false);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [tier, setTierState] = useState<Tier>("small");

  useEffect(() => {
    getMeta()
      .then((m) => {
        setMeta(m);
        if (m.tier) setTierState(m.tier);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    localStorage.setItem(LENGTH_KEY, String(length));
  }, [length]);

  useEffect(() => {
    localStorage.setItem(STEPS_KEY, String(maxSteps));
  }, [maxSteps]);

  // ?race=<id> 恢复一局（对局可分享/可刷新不丢）
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("race");
    if (id) void restore(id);
  }, [restore]);

  const hasRace = state.raceId !== null;

  /* 设置改动一律「换一局」，而不是把控件锁死。
     人机对战里改了就重开（名次表、谜底都变了）；出题模式里改了就清空，
     因为题目是用户自己填的，重开只会把填好的谜底弄丢。 */
  const restart = (nextMode: Mode = mode, nextLen = length, nextSteps = maxSteps) => {
    void begin(nextMode, nextSteps, { minLen: nextLen, maxLen: nextLen });
  };

  const onModeChange = (next: Mode) => {
    setMode(next);
    if (hasRace) reset(next);
  };

  const onLengthChange = (n: number) => {
    setLength(n);
    if (hasRace && mode === "versus") restart(mode, n);
  };

  const onMaxStepsChange = (n: number) => {
    setMaxSteps(n);
    if (hasRace && mode === "versus") restart(mode, length, n);
  };

  const onTierChange = async (next: Tier) => {
    if (next === tier) return;
    try {
      await setTier(next);
      setTierState(next);
      setMeta(await getMeta());
      // 名次表按旧词池建的，继续玩会对不上，直接重开
      if (hasRace && mode === "versus") restart();
    } catch {
      /* 失败保持原档位 */
    }
  };

  /* 顶栏「重开」：人机对战换一个谜底重新开始；
     出题模式则清空棋盘，等用户自己填题——重开不该替用户选一道题。 */
  const onNew = () => {
    if (mode === "challenge") reset("challenge");
    else restart();
  };

  return (
    <div className="flex flex-col lg:h-dvh">
      <div className="arena-backdrop" />

      <Header
        mode={mode}
        onModeChange={onModeChange}
        length={length}
        onLengthChange={onLengthChange}
        maxSteps={maxSteps}
        onMaxStepsChange={onMaxStepsChange}
        onNew={onNew}
        onToggleTheme={toggle}
        dark={theme === "dark"}
        meta={meta}
        phase={state.phase}
        tier={tier}
        onTierChange={onTierChange}
      />

      {/* 桌面端整页锁在一屏内，长表在面板内部滚动——
          否则 Agent 一局交 70 个词，整页被撑长，输入框跑到屏幕外。
          高度由外层 flex 分配，不硬编码顶栏高度（顶栏会因换行变高）。 */}
      <main className="mx-auto flex w-full max-w-[1400px] flex-col px-4 pb-3 lg:min-h-0 lg:flex-1">
        {state.error && (
          <div className="mt-2 flex items-start justify-between gap-3 rounded-xl border border-rose-500/35 bg-rose-500/10 px-4 py-2 text-sm text-rose-300">
            <span>{state.error}</span>
            <button className="text-xs underline opacity-70" onClick={clearError}>关闭</button>
          </div>
        )}

        {state.phase === "finished" && state.target && (
          <RoundResult
            target={state.target}
            winner={state.winner}
            mode={state.mode}
            humanWords={state.humanWords}
            agentWords={state.agentWords}
            humanSolved={state.humanSolved}
            agentSolved={state.agentSolved}
            onAgain={onNew}
          />
        )}

        {mode === "challenge" && (
          <div className="pt-3">
            <ChallengeBar
              started={hasRace}
              target={state.phase === "finished" ? state.target : null}
              busy={state.busy}
              onChallenge={(t) => void begin("challenge", maxSteps, { targetWord: t })}
            />
          </div>
        )}

        <div
          className={
            "grid gap-3 pt-3 max-lg:auto-rows-[minmax(28rem,auto)] lg:min-h-0 lg:flex-1 " +
            (mode === "versus" ? "lg:grid-cols-2" : "")
          }
        >
          {mode === "versus" && (
            <HumanPanel
              rows={Object.values(state.human)}
              words={state.humanWords}
              done={state.humanDone}
              solved={state.humanSolved}
              started={hasRace}
              targetLength={hasRace ? state.targetLength : length}
              onGuess={(w) => void guess(w, { mode, maxSteps, minLen: length, maxLen: length })}
              onGiveup={giveup}
              busy={state.busy}
            />
          )}

          <AgentPanel
            rows={Object.values(state.agent)}
            words={state.agentWords}
            step={state.step}
            maxSteps={state.maxSteps || maxSteps}
            solved={state.agentSolved}
            done={state.agentDone}
            logs={state.logs}
            revealed={state.revealAgent}
            running={state.phase === "running"}
            started={hasRace}
            onReveal={() => setReveal(true)}
          />
        </div>

        <footer className="mt-2 flex flex-wrap items-center justify-between gap-2 px-1 text-[11px] text-[rgb(var(--fg-faint))]">
          <span>
            谜底受限，猜词不限 —— 词库里没有的词也照常算相似度。胜负看
            <span className="text-[rgb(var(--fg-muted))]">猜中时用掉的词数</span>，少者胜。
          </span>
          <button
            className="underline decoration-dotted hover:text-[rgb(var(--fg-muted))]"
            onClick={() => setPoolOpen(true)}
          >
            词池与引擎
          </button>
        </footer>
      </main>

      <PoolSheet meta={meta} hidden={poolOpen} onClose={() => setPoolOpen(false)} />
    </div>
  );
}
