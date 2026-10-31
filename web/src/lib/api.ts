import type { GuessRecord, Meta, Mode, RaceSnapshot } from "../types";

const BASE = "/api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let message = `请求失败 (${res.status})`;
    try {
      const body = await res.json();
      const detail = body?.detail;
      if (typeof detail === "string") message = detail;
      else if (Array.isArray(detail) && detail[0]?.msg) {
        // pydantic 的 "Value error, xxx" 前缀对用户没意义
        message = String(detail[0].msg).replace(/^Value error,\s*/, "");
      }
    } catch {
      /* 保持默认文案 */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export const createRace = (opts: {
  mode: Mode;
  maxSteps: number;
  targetWord?: string;
  minLen?: number;
  maxLen?: number;
}) =>
  req<RaceSnapshot>("/race", {
    method: "POST",
    body: JSON.stringify({
      mode: opts.mode,
      max_steps: opts.maxSteps,
      target_word: opts.targetWord,
      min_len: opts.minLen ?? 2,
      max_len: opts.maxLen ?? 4,
    }),
  });

export const startAgent = (id: string) =>
  req<{ ok: boolean }>(`/race/${id}/start`, { method: "POST" });

export const sendGuess = (id: string, word: string) =>
  req<{ guess: GuessRecord; human_done: boolean; human_guesses: number }>(
    `/race/${id}/guess`,
    { method: "POST", body: JSON.stringify({ word }) },
  );

export const giveUp = (id: string) =>
  req<{ human_done: boolean }>(`/race/${id}/giveup`, { method: "POST" });

export const getMeta = () => req<Meta>("/meta");

export const getRace = (id: string) => req<RaceSnapshot>(`/race/${id}`);

export const getPoolSample = (length?: number) =>
  req<{ count: number; sample: string[] }>(
    `/pool/sample?n=16${length ? `&length=${length}` : ""}`,
  );

export const eventSource = (id: string) => new EventSource(`/api/race/${id}/events`);
