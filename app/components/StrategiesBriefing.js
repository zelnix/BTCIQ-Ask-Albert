'use client';
// "How your strategies are playing out" — a compact briefing panel for the Morning
// Brief. Deterministic: reads GET /api/v1/albert/strategy/briefing (active baskets'
// live P&L + rule-based actions/watch-outs). Pinning/eligibility unaffected.
import React from 'react';
import { API_BASE, getPid } from '../lib/api';
import { Layers, TrendingUp, TrendingDown, AlertTriangle, Eye, ArrowRight, Loader2, Sparkles } from 'lucide-react';

const pct = (n) => (n == null || isNaN(n)) ? '—' : `${n >= 0 ? '+' : ''}${Number(n).toFixed(1)}%`;
const usd = (n) => (n == null || isNaN(n)) ? '—' : `${n >= 0 ? '+' : '-'}$${Math.abs(Number(n)).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

export default function StrategiesBriefing({ onNav }) {
  const [data, setData] = React.useState(null);
  const [err, setErr] = React.useState(false);

  React.useEffect(() => {
    const pid = getPid();
    if (!pid) { setData({ hasStrategies: false, strategies: [], actions: [] }); return; }
    fetch(`${API_BASE}/v1/albert/strategy/briefing?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => setData(j && j.status === 'ready' ? j : { hasStrategies: false, strategies: [], actions: [] }))
      .catch(() => setErr(true));
  }, []);

  const go = () => onNav && onNav('strategies');

  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950/40">
      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950/60 px-3 py-2">
        <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-300">
          <Layers className="h-3.5 w-3.5 text-violet-300" />Your strategies
        </span>
        {data?.hasStrategies && (
          <span className={`text-[12px] font-bold ${data.totalPnlUsd >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
            {usd(data.totalPnlUsd)} <span className="text-[10px] font-medium text-slate-500">({pct(data.avgPnlPct)} avg)</span>
          </span>
        )}
      </div>

      {!data && !err && (
        <div className="flex items-center gap-2 px-3 py-6 text-[12px] text-slate-400"><Loader2 className="h-3.5 w-3.5 animate-spin" />Checking how your strategies are playing out…</div>
      )}

      {(err || (data && !data.hasStrategies)) && (
        <div className="px-3 py-5 text-center">
          <Sparkles className="mx-auto mb-1.5 h-5 w-5 text-violet-300" />
          <p className="text-[12px] text-slate-300">No active strategies yet.</p>
          <p className="mx-auto mt-0.5 max-w-[15rem] text-[11px] text-slate-500">Build a multi-coin strategy with Albert and this brief will track how it&apos;s playing out each morning.</p>
          <button onClick={go} className="mt-2 inline-flex items-center gap-1 rounded-lg border border-violet-500/40 bg-violet-500/10 px-2.5 py-1 text-[11px] font-semibold text-violet-200 hover:bg-violet-500/20">
            Build a strategy <ArrowRight className="h-3 w-3" />
          </button>
        </div>
      )}

      {data && data.hasStrategies && (
        <div className="divide-y divide-slate-800/70">
          {/* Per-strategy P&L rows */}
          <div className="space-y-1.5 px-3 py-2">
            {data.strategies.map((s) => (
              <button key={s.id} onClick={go} className="flex w-full items-center justify-between gap-2 text-left">
                <span className="flex min-w-0 items-center gap-1.5">
                  {s.pnlPct >= 0 ? <TrendingUp className="h-3.5 w-3.5 shrink-0 text-emerald-400" /> : <TrendingDown className="h-3.5 w-3.5 shrink-0 text-rose-400" />}
                  <span className="truncate text-[13px] font-medium text-slate-200">{s.title}</span>
                  <span className="shrink-0 text-[10px] text-slate-500">{s.legCount} coin{s.legCount === 1 ? '' : 's'} · {s.daysActive}d</span>
                </span>
                <span className={`shrink-0 text-[12px] font-bold ${s.pnlPct >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>{pct(s.pnlPct)}</span>
              </button>
            ))}
          </div>

          {/* Actions / watch-outs */}
          {data.actions && data.actions.length > 0 ? (
            <div className="space-y-1 px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Actions &amp; watch-outs</p>
              {data.actions.map((a, i) => (
                <div key={i} className="flex items-start gap-1.5 text-[12px] leading-snug">
                  {a.level === 'action'
                    ? <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-400" />
                    : <Eye className="mt-0.5 h-3 w-3 shrink-0 text-sky-400" />}
                  <span className={a.level === 'action' ? 'text-amber-100' : 'text-slate-300'}>{a.text}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="px-3 py-2 text-[12px] text-slate-400">Nothing needs action right now — your strategies are on track. Stay patient.</div>
          )}

          <button onClick={go} className="flex w-full items-center justify-center gap-1 px-3 py-2 text-[11px] font-semibold text-sky-400 hover:text-sky-300">
            Open Trading Strategies <ArrowRight className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  );
}
