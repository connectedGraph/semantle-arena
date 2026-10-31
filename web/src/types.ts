export type Level = "exact" | "hot" | "warm" | "cold";
export type Tier = "small" | "medium" | "full";

export interface GuessRecord {
  order: number;
  word: string;
  similarity: number;
  /** 归一化显示百分比（本局最接近的词 = 99%） */
  similarity_pct: number;
  /** 原始余弦百分比，用于排查 */
  raw_pct: number;
  rank: number | null;
  level: Level;
  is_target: boolean;
  source: "human" | "agent";
  at: number;
  step?: number | null;
  /** 池外词：分数由汉字向量平均估算，只是近似 */
  approx?: boolean;
}

export type Mode = "versus" | "challenge";
export type Phase = "idle" | "running" | "finished";

export interface RaceSnapshot {
  race_id: string;
  mode: Mode;
  max_steps: number;
  target_length: number;
  target: string | null;
  started: boolean;
  finished: boolean;
  winner: "human" | "agent" | "tie" | null;
  human_done: boolean;
  agent_done: boolean;
  human_solved: boolean;
  agent_solved: boolean;
  human_guesses: number;
  agent_guesses: number;
  human_turns: number;
  agent_turns: number;
  human_history: GuessRecord[];
  agent_history: GuessRecord[];
}

export type AgentEvent =
  | { type: "snapshot" } & RaceSnapshot
  | { type: "start"; max_steps: number }
  | { type: "step"; step: number; max_steps: number }
  | { type: "assistant"; step: number; text: string }
  | { type: "tool_call"; id: string; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; id: string; name: string; text: string; rows: GuessRow[] }
  | { type: "human_guess"; guess: GuessRecord }
  | { type: "human_done" }
  | { type: "solved"; step: number; guesses: number }
  | { type: "agent_done"; solved: boolean; steps: number; guesses: number }
  | {
      type: "race_end";
      target: string;
      winner: "human" | "agent" | "tie" | null;
      human_guesses: number;
      agent_guesses: number;
      human_turns: number;
      agent_turns: number;
      human_solved: boolean;
      agent_solved: boolean;
    }
  | { type: "error"; message: string };

export interface GuessRow {
  word: string;
  similarity_pct: number;
  raw_pct?: number;
  rank: number | null;
  level: Level;
  is_target: boolean;
  reused?: boolean;
}

export interface LogEntry {
  id: string;
  kind: "assistant" | "call" | "result" | "step" | "error";
  step?: number;
  text: string;
  name?: string;
  args?: Record<string, unknown>;
  rows?: GuessRow[];
}

export interface Meta {
  pool: {
    generated_at: string;
    params: { min_freq: number; min_len: number; max_len: number };
    count: number;
    /** 全池词数（当前档位可能小于它） */
    pool_total: number;
    by_length: Record<string, number>;
    tier: Tier;
    tiers: Record<string, number>;
    vector_coverage: number;
    engine: string;
  };
  config: { char_penalty: number; semantic_blend: number };
  models: { embedding: string; agent: string };
  tier: Tier;
  tiers: Record<string, number>;
}
