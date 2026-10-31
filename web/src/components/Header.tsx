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
  phase: "idle" | "running" | "finished";
  tier: Tier;
  onTierChange: (t: Tier) => void;
}

const LENGTHS = [2, 3, 4];
const STEPS = [12, 30, 50];

const TIER_LABELS: Record<Tier, string> = {
  small: "精简",
  medium: "标准",
  full: "完整",
};

/**
 * 顶部控制条。
 *
 * 这里所有控件在对局中都可用——改了就换一局，而不是灰掉。
 * 灰掉的控件意味着「你得先结束才能改」，那是一次无谓的额外操作。
 */
export function Header(props: Props) {
  const { mode, onModeChange, length, onLengthChange, maxSteps, onMaxStepsChange,
          onNew, onToggleTheme, dark, meta, phase,
          tier, onTierChange } = props;

  const tierCounts = meta?.tiers ?? {};
  const poolCount = meta?.pool.count;

  return (
    <header className="sticky top-0 z-20 border-b border-[rgb(var(--border))] bg-[rgb(var(--bg-veil))]/70 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2">
        <h1 className="mr-1 flex items-baseline gap-2 text-[16px] font-semibold tracking-tight">
          <span className="text-gradient">Semantle</span>
          <span className="text-[rgb(var(--fg-muted))]">Arena</span>
        </h1>

        <div className="segmented" role="group" aria-label="模式">
          <button aria-pressed={mode === "versus"} onClick={() => onModeChange("versus")}>
            人机对战
          </button>
          <button aria-pressed={mode === "challenge"} onClick={() => onModeChange("challenge")}>
            我出题
          </button>
        </div>

        <Group label="词库">
          {(["small", "medium", "full"] as Tier[]).map((t) => (
            <button key={t} aria-pressed={tier === t} onClick={() => onTierChange(t)}
                    title={`${(tierCounts[t] ?? 0).toLocaleString()} 词`}>
              {TIER_LABELS[t]}
            </button>
          ))}
        </Group>

        <Group label="字数">
          {LENGTHS.map((n) => (
            <button key={n} aria-pressed={length === n} onClick={() => onLengthChange(n)}>
              {n}
            </button>
          ))}
        </Group>

        {mode === "versus" && (
          <Group label="Agent 步数上限">
            {STEPS.map((n) => (
              <button key={n} aria-pressed={maxSteps === n} onClick={() => onMaxStepsChange(n)}>
                {n}
              </button>
            ))}
          </Group>
        )}

        <div className="ml-auto flex items-center gap-2">
          {poolCount ? (
            <span className="hidden text-[11px] tabular-nums text-[rgb(var(--fg-faint))] md:inline">
              {poolCount.toLocaleString()} 词
            </span>
          ) : null}
          <button
            className="btn btn-ghost !px-2 !py-1.5"
            onClick={onToggleTheme}
            aria-label={dark ? "切到浅色" : "切到深色"}
            title={dark ? "切到浅色" : "切到深色"}
          >
            {dark ? "☀" : "☾"}
          </button>
          {/* 开局前不放按钮：人机对战输入第一个词即开局，出题模式提交谜底即开局 */}
          {phase !== "idle" && (
            <button className="btn btn-primary !py-1.5" onClick={onNew}>
              重开
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[11px] text-[rgb(var(--fg-faint))]">{label}</span>
      <div className="segmented" role="group" aria-label={label}>
        {children}
      </div>
    </div>
  );
}
