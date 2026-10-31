import { useEffect, useState } from "react";
import type { Meta } from "../types";
import { getPoolSample } from "../lib/api";

interface Props {
  meta: Meta | null;
  hidden: boolean;
  onClose: () => void;
}

/**
 * 词池说明面板：让「词表有多全」这件事可被验证，而不是一句宣传语。
 * 数据全部来自 /api/meta 与 /api/pool/sample。
 */
export function PoolSheet({ meta, hidden, onClose }: Props) {
  const [samples, setSamples] = useState<Record<number, { count: number; sample: string[] }>>({});

  useEffect(() => {
    if (!hidden) return;
    let alive = true;
    Promise.all([2, 3, 4].map((n) => getPoolSample(n)))
      .then(([a, b, c]) => {
        if (!alive) return;
        setSamples({ 2: a, 3: b, 4: c });
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [hidden]);

  if (!hidden) return null;

  const p = meta?.pool;

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-black/55 p-4 backdrop-blur-[2px]"
         onClick={onClose}>
      <div className="glass glass-hi rise w-full max-w-lg overflow-hidden"
           role="dialog" aria-modal="true" aria-label="词池说明"
           onClick={(e) => e.stopPropagation()}>
        <header className="flex items-center justify-between border-b border-[rgb(var(--border))] px-5 py-3.5">
          <h2 className="text-sm font-semibold">词池与引擎</h2>
          <button className="btn btn-ghost !px-2 !py-1 text-xs" onClick={onClose}>关闭</button>
        </header>

        <div className="space-y-4 px-5 py-4 text-sm">
          {p ? (
            <>
              <div className="grid grid-cols-3 gap-2">
                {[2, 3, 4].map((n) => (
                  <div key={n} className="rounded-xl border border-[rgb(var(--border))] px-3 py-2">
                    <p className="text-[11px] text-[rgb(var(--fg-faint))]">{n} 字谜底</p>
                    <p className="mt-0.5 text-lg font-semibold tabular-nums">
                      {(p.by_length[String(n)] ?? 0).toLocaleString()}
                    </p>
                  </div>
                ))}
              </div>

              <dl className="space-y-1.5 text-xs">
                <Row k="谜底总数" v={p.count.toLocaleString()} />
                <Row k="构建口径" v={`词频 ≥ ${p.params.min_freq} · ${p.params.min_len}~${p.params.max_len} 字 · 名词/动词/形容词`} />
                <Row k="生成时间" v={p.generated_at} />
                <Row k="语义模型" v={meta.models.embedding} />
                <Row k="对弈模型" v={meta.models.agent} />
              </dl>
            </>
          ) : (
            <p className="text-xs text-[rgb(var(--fg-faint))]">加载中…</p>
          )}

          <div>
            <p className="mb-2 text-xs text-[rgb(var(--fg-muted))]">
              谜底受限，<span className="text-[rgb(var(--fg))]">猜词不限</span>：
              输入词池里没有的词也照常算相似度，所以「干饭搭子」这种表达也能试。
            </p>
            <div className="space-y-2">
              {[2, 3, 4].map((n) => (
                <div key={n} className="rounded-xl border border-[rgb(var(--border))] px-3 py-2">
                  <p className="mb-1 text-[11px] text-[rgb(var(--fg-faint))]">
                    {n} 字抽样
                    {samples[n] && ` · 共 ${samples[n].count.toLocaleString()}`}
                  </p>
                  <p className="flex flex-wrap gap-1">
                    {(samples[n]?.sample ?? []).map((w) => (
                      <span key={w} className="rounded-md bg-[rgb(var(--fg)/0.06)] px-1.5 py-0.5 text-[11px]">
                        {w}
                      </span>
                    ))}
                    {!samples[n] && <span className="text-[11px] text-[rgb(var(--fg-faint))]">…</span>}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-[rgb(var(--fg-faint))]">{k}</dt>
      <dd className="text-right text-[rgb(var(--fg-muted))]">{v}</dd>
    </div>
  );
}
