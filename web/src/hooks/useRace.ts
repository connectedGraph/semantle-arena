import { useCallback, useEffect, useReducer, useRef } from "react";
import type {
  AgentEvent, GuessRecord, GuessRow, Level, LogEntry, Mode, RaceSnapshot,
} from "../types";
import { abortRace, createRace, eventSource, getRace, giveUp, sendGuess, startAgent } from "../lib/api";

interface State {
  phase: "idle" | "running" | "finished";
  raceId: string | null;
  mode: Mode;
  targetLength: number;
  target: string | null;
  maxSteps: number;

  human: Record<string, GuessRecord>;
  agent: Record<string, GuessRecord>;
  /** 已提交的词数（Agent 侧不含重复提交，命中那一刻为止的口径与后端一致） */
  humanWords: number;
  agentWords: number;
  humanDone: boolean;
  agentDone: boolean;
  humanSolved: boolean;
  agentSolved: boolean;

  step: number;
  logs: LogEntry[];
  /** 是否公开 Agent 的猜测与推理。默认关闭——对局中看对手答案就没得比了。 */
  revealAgent: boolean;
  winner: "human" | "agent" | "tie" | null;

  error: string | null;
  busy: boolean;
}

type Action =
  | { type: "reset"; mode: Mode; maxSteps: number; targetLength: number }
  | { type: "created"; raceId: string; mode: Mode; maxSteps: number; targetLength: number }
  | { type: "running" }
  | { type: "humanGuess"; guess: GuessRecord; done: boolean }
  | { type: "humanGiveup" }
  | { type: "event"; event: AgentEvent }
  | { type: "setReveal"; value: boolean }
  | { type: "error"; message: string | null }
  | { type: "busy"; value: boolean }
  | { type: "restore"; snapshot: RaceSnapshot };

const EMPTY: State = {
  phase: "idle",
  raceId: null,
  mode: "versus",
  targetLength: 2,
  target: null,
  maxSteps: 30,
  human: {},
  agent: {},
  humanWords: 0,
  agentWords: 0,
  humanDone: false,
  agentDone: false,
  humanSolved: false,
  agentSolved: false,
  step: 0,
  logs: [],
  revealAgent: false,
  winner: null,
  error: null,
  busy: false,
};

const MAX_LOGS = 240;

function addGuess(
  map: Record<string, GuessRecord>,
  guess: GuessRecord,
): { map: Record<string, GuessRecord>; added: boolean } {
  if (map[guess.word]) return { map, added: false };
  return { map: { ...map, [guess.word]: guess }, added: true };
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "reset":
      return { ...EMPTY, mode: action.mode, maxSteps: action.maxSteps,
               targetLength: action.targetLength, revealAgent: state.revealAgent };
    case "created":
      return {
        ...EMPTY,
        revealAgent: state.revealAgent,
        raceId: action.raceId,
        mode: action.mode,
        maxSteps: action.maxSteps,
        targetLength: action.targetLength,
      };
    case "running":
      return { ...state, phase: "running", busy: false };
    case "humanGuess": {
      const { map, added } = addGuess(state.human, action.guess);
      return {
        ...state,
        human: map,
        humanWords: state.humanWords + (added ? 1 : 0),
        humanDone: action.done || state.humanDone,
        humanSolved: state.humanSolved || action.guess.is_target,
        busy: false,
      };
    }
    case "humanGiveup":
      return { ...state, humanDone: true, busy: false };
    case "setReveal":
      return { ...state, revealAgent: action.value };
    case "error":
      return { ...state, error: action.message, busy: false };
    case "busy":
      return { ...state, busy: action.value };
    case "restore": {
      const snap = action.snapshot;
      const human: Record<string, GuessRecord> = {};
      for (const g of snap.human_history) human[g.word] = g;
      const agent: Record<string, GuessRecord> = {};
      for (const g of snap.agent_history) agent[g.word] = g;
      return {
        ...EMPTY,
        revealAgent: snap.finished,
        raceId: snap.race_id,
        mode: snap.mode,
        maxSteps: snap.max_steps,
        targetLength: snap.target_length,
        target: snap.target,
        phase: snap.finished ? "finished" : "running",
        human,
        agent,
        humanWords: snap.human_words,
        agentWords: snap.agent_words,
        humanDone: snap.human_done,
        agentDone: snap.agent_done,
        humanSolved: snap.human_solved,
        agentSolved: snap.agent_solved,
        winner: snap.winner,
      };
    }
    case "event":
      return applyEvent(state, action.event);
    default:
      return state;
  }
}

function applyEvent(state: State, ev: AgentEvent): State {
  const pushLog = (entry: LogEntry) => [...state.logs, entry].slice(-MAX_LOGS);

  switch (ev.type) {
    case "start":
      return { ...state, phase: "running", maxSteps: ev.max_steps };

    case "step":
      return { ...state, step: ev.step };

    case "assistant":
      return {
        ...state,
        logs: pushLog({ id: `a-${ev.step}-${state.logs.length}`, kind: "assistant",
                        step: ev.step, text: ev.text }),
      };

    case "tool_call":
      return {
        ...state,
        logs: pushLog({
          id: `c-${ev.id}`,
          kind: "call",
          name: ev.name,
          args: ev.args,
          text: describeCall(ev.name, ev.args),
        }),
      };

    case "tool_result": {
      const logs = pushLog({
        id: `r-${ev.id}`,
        kind: "result",
        name: ev.name,
        rows: ev.rows,
        text: summarize(ev.rows),
      });
      // 工具结果里出现的新词，同步到 Agent 猜词表。
      // reused 是「这个词之前猜过」，不增加词数——与后端 until_solved_guesses 同口径。
      let agent = state.agent;
      let solved = state.agentSolved;
      let added = 0;
      for (const row of ev.rows ?? []) {
        if (row.reused) continue;
        const res = addGuess(agent, {
          order: Object.keys(agent).length + 1,
          word: row.word,
          similarity: row.similarity_pct / 100,
          similarity_pct: row.similarity_pct,
          raw_pct: row.raw_pct ?? row.similarity_pct,
          rank: row.rank,
          level: row.level,
          is_target: row.is_target,
          source: "agent",
          at: Date.now() / 1000,
        });
        agent = res.map;
        if (res.added) added += 1;
        if (row.is_target) solved = true;
      }
      return { ...state, logs, agent, agentWords: state.agentWords + added, agentSolved: solved };
    }

    case "solved":
      return { ...state, agentSolved: true };

    case "agent_done":
      return { ...state, agentDone: true, agentSolved: state.agentSolved || ev.solved };

    case "human_done":
      return { ...state, humanDone: true };

    case "race_end":
      return {
        ...state,
        phase: "finished",
        target: ev.target,
        winner: ev.winner,
        humanDone: true,
        agentDone: true,
        // 结算时自动揭晓 Agent 的猜测与轨迹：比赛结束了，藏就没意义了
        revealAgent: true,
        humanSolved: ev.human_solved,
        agentSolved: ev.agent_solved,
        humanWords: ev.human_solved ? ev.human_words || state.humanWords : state.humanWords,
        agentWords: ev.agent_solved ? ev.agent_words || state.agentWords : state.agentWords,
      };

    case "error":
      return {
        ...state,
        error: ev.message,
        logs: pushLog({ id: `e-${state.logs.length}`, kind: "error",
                        text: ev.message }),
      };

    default:
      return state;
  }
}

function describeCall(name: string, args: Record<string, unknown>): string {
  if (name === "guess") {
    const words = (args?.words as string[]) ?? [];
    return `猜 ${words.length} 个词：${words.join("、")}`;
  }
  if (name === "review") {
    const k = args?.k ?? -1;
    return k === -1 ? "回顾全部已猜词" : `回顾最接近的前 ${k} 个`;
  }
  return name;
}

function summarize(rows: GuessRow[] | undefined): string {
  if (!rows?.length) return "（无结果）";
  const hit = rows.find((r) => r.is_target);
  if (hit) return `命中答案：${hit.word}`;
  const best = rows.reduce<GuessRow | null>(
    (acc, r) => (!acc || (r.rank ?? 1e9) < (acc.rank ?? 1e9) ? r : acc),
    null,
  );
  return best
    ? `${rows.length} 条结果，最接近 ${best.word}（${best.similarity_pct.toFixed(2)}%）`
    : `${rows.length} 条结果`;
}

export interface BeginOpts {
  mode?: Mode;
  maxSteps?: number;
  targetWord?: string;
  minLen?: number;
  maxLen?: number;
}

export function useRace() {
  const [state, dispatch] = useReducer(reducer, EMPTY);
  const esRef = useRef<EventSource | null>(null);
  // 用 ref 拿最新 raceId：begin 之后立刻 guess 时，state 还没重渲染
  const raceRef = useRef<string | null>(null);

  const closeStream = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  const openStream = useCallback(
    (id: string) => {
      closeStream();
      const es = eventSource(id);
      esRef.current = es;
      es.onmessage = (msg: MessageEvent) => {
        try {
          const ev = JSON.parse(msg.data) as AgentEvent;
          if (ev.type === "snapshot") return;
          dispatch({ type: "event", event: ev });
          if (ev.type === "race_end") {
            es.close();
            esRef.current = null;
          }
        } catch {
          /* 忽略坏帧 */
        }
      };
      es.onerror = () => {
        /* 浏览器会自动重连；对局结束后服务端会关闭 */
      };
    },
    [closeStream],
  );

  useEffect(() => closeStream, [closeStream]);

  /** 开一局，返回 race_id（失败返回 null）。 */
  const begin = useCallback(
    async (mode: Mode, maxSteps: number, opts?: BeginOpts): Promise<string | null> => {
      // 上一局还没跑完就别留着了：Agent 循环会一直烧模型调用
      if (raceRef.current) void abortRace(raceRef.current);
      closeStream();
      raceRef.current = null;
      dispatch({ type: "reset", mode, maxSteps, targetLength: opts?.minLen ?? 2 });
      dispatch({ type: "busy", value: true });
      try {
        const snap = await createRace({
          mode,
          maxSteps,
          targetWord: opts?.targetWord,
          minLen: opts?.minLen,
          maxLen: opts?.maxLen,
        });
        raceRef.current = snap.race_id;
        dispatch({
          type: "created",
          raceId: snap.race_id,
          mode,
          maxSteps,
          targetLength: snap.target_length,
        });
        openStream(snap.race_id);
        dispatch({ type: "running" });
        await startAgent(snap.race_id);
        return snap.race_id;
      } catch (err) {
        dispatch({ type: "error", message: (err as Error).message });
        return null;
      }
    },
    [closeStream, openStream],
  );

  const guessIn = useCallback(async (id: string, word: string) => {
    dispatch({ type: "busy", value: true });
    try {
      const res = await sendGuess(id, word);
      dispatch({ type: "humanGuess", guess: res.guess, done: res.human_done });
      return res.guess;
    } catch (err) {
      dispatch({ type: "error", message: (err as Error).message });
      return null;
    }
  }, []);

  /** 猜一个词；还没开局就先开局再猜，省掉「先点开始」这一步。 */
  const guess = useCallback(
    async (word: string, opts?: BeginOpts) => {
      const id = raceRef.current;
      if (!id) {
        const created = await begin(opts?.mode ?? "versus", opts?.maxSteps ?? 30, opts);
        if (created) await guessIn(created, word);
        return;
      }
      await guessIn(id, word);
    },
    [begin, guessIn],
  );

  const giveup = useCallback(async () => {
    const id = raceRef.current;
    if (!id) return;
    dispatch({ type: "busy", value: true });
    try {
      await giveUp(id);
      dispatch({ type: "humanGiveup" });
    } catch (err) {
      dispatch({ type: "error", message: (err as Error).message });
    }
  }, []);

  const restore = useCallback(async (id: string) => {
    try {
      const snap = await getRace(id);
      raceRef.current = snap.race_id;
      dispatch({ type: "restore", snapshot: snap });
      if (!snap.finished) openStream(id);
    } catch (err) {
      dispatch({ type: "error", message: (err as Error).message });
    }
  }, [openStream]);

  const setReveal = useCallback((value: boolean) => {
    dispatch({ type: "setReveal", value });
  }, []);

  /** 回到空棋盘（换模式时用）：不新开局，等用户自己提交第一个词或谜底。 */
  const reset = useCallback((mode: Mode) => {
    const old = raceRef.current;
    if (old) void abortRace(old);   // 别让没人看的对局在后台继续烧 token
    closeStream();
    raceRef.current = null;
    dispatch({ type: "reset", mode, maxSteps: 30, targetLength: 2 });
  }, [closeStream]);

  return {
    state,
    begin,
    restore,
    guess,
    giveup,
    setReveal,
    reset,
    clearError: () => dispatch({ type: "error", message: null }),
  };
}

export const LEVEL_ORDER: Record<Level, number> = {
  exact: 0,
  hot: 1,
  warm: 2,
  cold: 3,
};
