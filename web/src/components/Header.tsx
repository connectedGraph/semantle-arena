import type { Meta, Mode, Tier } from "../types";

interface Props {
  mode: Mode;
  onModeChange: (m: Mode) => void;
  length: number;
  onLengthChange: (n: number) => void;
  maxSteps: number;
  onMaxStepsChange: (n: number) => void;
  onNew: () => void;
  onToggleTheme: () => void;
  dark: boolean;
  meta: Meta | null;
  locked: boolean;
  phase: "idle" | "running" | "finished";
  tier: Tier;
  onTierChange: (t: Tier) => void;
}

const LENGTHS = [2, 3, 4];
const STEPS = [12, 30, 50];

/** 档位的展示名与一句话说明，鼠标悬停时给提示 */
const TIER_LABELS: Record<Tier, { name: string; hint: string }> = {
  small: { name: "精简", hint: "3000 个日常具象词，抽到的你都认识" },
  medium: { name: "标准", hint: "8000 词，够玩又有一定挑战" },
  full: { name: "完整", hint: "1.6 万词，会抽到冷门词" },
};

export function Header(props: Props) {
  const { mode, onModeChange, length, onLengthChange, maxSteps, onMaxStepsChange,
          onNew, onToggleTheme, dark, meta, locked, phase,
          tier, onTierChange } = props;

  const tierCounts = meta?.tiers ?? {};

  return (
    <header className="sticky top-0 z-20 border-b border-[rgb(var(--border))] bg-[rgb(var(--bg-veil))]/70 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-5 gap-y-2 px-5 py-2.5">
        <div className="flex items-baseline gap-2.5">
          <h1 className="text-[17px] font-semibold tracking-tight">
            <span className="text-gradient">Semantle</span>
            <span className="ml-1 text-[rgb(var(--fg-muted))]">Arena</span>
          </h1>
          <span className="hidden text-[11px] text-[rgb(var(--fg-faint))] sm:inline">
            人机语义猜词对抗
          </span>
        </div>

        <div className="segmented" role="group" aria-label="模式">
          <button aria-pressed={mode === "versus"} disabled={locked}
                  onClick={() => onModeChange("versus")}>
            人机对战
          </button>
          <button aria-pressed={mode === "challenge"} disabled={locked}
                  onClick={() => onModeChange("challenge")}>
            我出题
          </button>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-[rgb(var(--fg-faint))]">词库</span>
          <div className="segmented" role="group" aria-label="词库档位">
            {(["small", "medium", "full"] as Tier[]).map((t) => (
              <button key={t} aria-pressed={tier === t} disabled={locked}
                      onClick={() => onTierChange(t)}
                      title={TIER_LABELS[t].hint}>
                {TIER_LABELS[t].name}
                {tierCounts[t] ? (
                  <span className="ml-1 opacity-45">
                    {Math.round(tierCounts[t] / 100) / 10}k
                  </span>
                ) : null}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-[rgb(var(--fg-faint))]">答案</span>
          <div className="segmented" role="group" aria-label="谜底字数">
            {LENGTHS.map((n) => (
              <button key={n} aria-pressed={length === n} disabled={locked}
                      onClick={() => onLengthChange(n)}>
                {n} 字
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-[rgb(var(--fg-faint))]">步数</span>
          <div className="segmented" role="group" aria-label="Agent 步数上限">
            {STEPS.map((n) => (
              <button key={n} aria-pressed={maxSteps === n} disabled={locked}
                      onClick={() => onMaxStepsChange(n)}>
                {n}
              </button>
            ))}
          </div>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {meta && (
            <span className="hidden text-[11px] text-[rgb(var(--fg-faint))] lg:inline">
              {(meta.pool.count / 1000).toFixed(1)}k 词 · {meta.models.agent.split("/").pop()}
            </span>
          )}
          <button
            className="btn btn-ghost !px-2 !py-1.5"
            onClick={onToggleTheme}
            aria-label={dark ? "切到浅色" : "切到深色"}
            title={dark ? "切到浅色" : "切到深色"}
          >
            {dark ? "☀" : "☾"}
          </button>
          <button className="btn btn-primary" onClick={onNew} disabled={locked}>
            {phase === "idle" ? "开始对局" : "新开一局"}
          </button>
        </div>
      </div>
    </header>
  );
}
