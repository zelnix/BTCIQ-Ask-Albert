'use client';

import React from 'react';
import { Target, TrendingUp, TrendingDown, CircleDot, X } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { API_BASE } from '../lib/api';
import AlbertText from './AlbertText';

export default function AlbertTrackRecord() {
  const [data, setData] = React.useState(null);
  const [selected, setSelected] = React.useState(null);

  const load = React.useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/v1/albert/track-record?limit=8`, { cache: 'no-store' });
      const j = await r.json();
      if (j.status === 'ready') setData(j);
    } catch (e) { /* noop */ }
  }, []);

  React.useEffect(() => { load(); const id = setInterval(load, 60000); return () => clearInterval(id); }, [load]);

  const hit = data && data.hit_rate;
  const nCalls = (data && data.n_calls) || 0;
  const open = (data && data.open) || [];
  const recent = (data && data.recent) || [];
  const trend = (data && data.trend) || [];

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Target className="h-4 w-4 text-violet-400" />
        <h3 className="text-sm font-semibold text-white">Albert&apos;s Track Record</h3>
        <span className="text-[10px] text-slate-500">how correct were his calls?</span>
      </div>

      {nCalls === 0 ? (
        <p className="text-xs text-slate-500">No calls logged yet. Ask Albert a buy/sell question — every directional call he makes is auto-logged and graded against real price once its horizon passes.</p>
      ) : (
        <>
          <div className="mb-3 flex items-center gap-4">
            <div>
              <p className="text-2xl font-bold text-white">{hit != null ? `${hit}%` : '—'}</p>
              <p className="text-[10px] text-slate-500">hit rate ({(data && data.n_graded) || 0} graded)</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-sky-300">{nCalls}</p>
              <p className="text-[10px] text-slate-500">calls tracked</p>
            </div>
            {data && data.avg_move != null && (
              <div>
                <p className={`text-2xl font-bold ${data.avg_move >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{data.avg_move > 0 ? '+' : ''}{data.avg_move}%</p>
                <p className="text-[10px] text-slate-500">avg move</p>
              </div>
            )}
          </div>

          {trend.length >= 2 && (
            <div className="mb-3">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Confidence trend (cumulative hit-rate)</p>
              <div className="h-24">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trend} margin={{ top: 4, right: 8, left: -22, bottom: 0 }}>
                    <XAxis dataKey="i" tick={{ fontSize: 9, fill: '#64748b' }} axisLine={false} tickLine={false} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#64748b' }} axisLine={false} tickLine={false} width={30} />
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 11 }} formatter={(v) => [`${v}%`, 'Hit rate']} labelFormatter={(l) => `Call #${l}`} />
                    <Line type="monotone" dataKey="hit_rate" stroke="#a78bfa" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {open.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">In progress</p>
              {open.map((c) => (
                <button key={c.id} onClick={() => setSelected(c)} className="flex w-full items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-2.5 py-1.5 text-left text-xs transition-colors hover:border-slate-700 hover:bg-slate-900">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${c.stance === 'buy' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'}`}>{c.stance}</span>
                  <span className="font-semibold text-slate-200">{c.asset}</span>
                  <span className="text-slate-500">@ ${Number(c.ref_price).toLocaleString()}</span>
                  <span className="ml-auto flex items-center gap-1">
                    {c.winning === true && <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />}
                    {c.winning === false && <TrendingDown className="h-3.5 w-3.5 text-red-400" />}
                    {c.live_pct != null && <span className={c.live_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}>{c.live_pct > 0 ? '+' : ''}{c.live_pct}%</span>}
                    <span className="text-[10px] text-slate-600">{c.horizon_days}d</span>
                  </span>
                </button>
              ))}
            </div>
          )}

          {recent.length > 0 && (
            <div className="mt-2 space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Graded</p>
              {recent.map((c) => (
                <button key={c.id} onClick={() => setSelected(c)} className="flex w-full items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-2.5 py-1.5 text-left text-xs transition-colors hover:border-slate-700 hover:bg-slate-900">
                  <CircleDot className={`h-3 w-3 ${c.outcome === 'correct' ? 'text-emerald-400' : 'text-red-400'}`} />
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${c.stance === 'buy' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'}`}>{c.stance}</span>
                  <span className="font-semibold text-slate-200">{c.asset}</span>
                  <span className={`ml-auto font-semibold ${c.outcome === 'correct' ? 'text-emerald-400' : 'text-red-400'}`}>{c.outcome === 'correct' ? 'Correct' : 'Missed'} · {c.pct_move > 0 ? '+' : ''}{c.pct_move}%</span>
                </button>
              ))}
            </div>
          )}
        </>
      )}
      {selected && <CallDetailModal call={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function PriceRung({ label, value, color }) {
  if (value == null) return null;
  return (
    <div className="flex items-center justify-between rounded-md bg-slate-950/50 px-2.5 py-1.5">
      <span className={`text-[11px] font-semibold ${color}`}>{label}</span>
      <span className="text-xs font-semibold text-slate-200">${Number(value).toLocaleString()}</span>
    </div>
  );
}

function CallDetailModal({ call, onClose }) {
  const c = call || {};
  const current = c.spot != null ? c.spot : c.eval_price;
  const graded = c.status === 'graded';
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900 p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className={`rounded px-2 py-0.5 text-[11px] font-bold uppercase ${c.stance === 'buy' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'}`}>{c.stance}</span>
            <span className="text-base font-bold text-white">{c.asset}</span>
            {c.conviction && <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400">{c.conviction} conviction</span>}
            {graded ? (
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${c.outcome === 'correct' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'}`}>{c.outcome === 'correct' ? 'Correct' : 'Missed'}</span>
            ) : (
              <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] font-semibold text-sky-300">In progress · {c.horizon_days}d</span>
            )}
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-slate-400 hover:text-white"><X className="h-4 w-4" /></button>
        </div>

        <div className="mb-3 grid grid-cols-2 gap-1.5">
          <PriceRung label="Take-profit / target" value={c.target} color="text-emerald-400" />
          <PriceRung label="Reference (entry)" value={c.ref_price} color="text-sky-300" />
          <PriceRung label="Invalidation / stop" value={c.invalidation} color="text-red-400" />
          <PriceRung label={graded ? 'Price at grading' : 'Current price'} value={current} color="text-amber-300" />
        </div>
        {(c.live_pct != null || c.pct_move != null) && (
          <p className="mb-3 text-xs text-slate-400">Move since call:{' '}
            <span className={`font-semibold ${((graded ? c.pct_move : c.live_pct) || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {(graded ? c.pct_move : c.live_pct) > 0 ? '+' : ''}{graded ? c.pct_move : c.live_pct}%
            </span>
          </p>
        )}

        {c.question && (
          <div className="mb-2">
            <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">You asked</p>
            <p className="text-xs italic text-slate-400">&ldquo;{c.question}&rdquo;</p>
          </div>
        )}
        <div>
          <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Albert&apos;s reasoning</p>
          <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-[13px] leading-relaxed text-slate-200">
            {c.reasoning ? <AlbertText text={c.reasoning} /> : <p className="text-slate-500">{c.summary || 'No reasoning captured for this call.'}</p>}
          </div>
        </div>
        {c.created_at && <p className="mt-3 text-center text-[10px] text-slate-600">Logged {new Date(c.created_at).toLocaleString()}</p>}
      </div>
    </div>
  );
}
