'use client';

import React from 'react';
import { CalendarDays, RefreshCw, History, ChevronDown, GitCompare, X, Check, LineChart as LineChartIcon } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { API_BASE } from '../lib/api';
import AlbertText from './AlbertText';

export default function WeeklyRecap() {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [history, setHistory] = React.useState([]);
  const [showHistory, setShowHistory] = React.useState(false);
  const [openId, setOpenId] = React.useState(null);
  const [compareMode, setCompareMode] = React.useState(false);
  const [picked, setPicked] = React.useState([]); // recap objects chosen to compare
  const [showCompare, setShowCompare] = React.useState(false);
  const [rangeW, setRangeW] = React.useState('all'); // 4 | 12 | all weeks on the season chart

  const loadHistory = React.useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/v1/albert/weekly-recap/history`, { cache: 'no-store' });
      const j = await r.json();
      setHistory((j && j.recaps) || []);
    } catch (e) { /* noop */ }
  }, []);

  const load = React.useCallback(async (refresh) => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/v1/albert/weekly-recap${refresh ? '?refresh=true' : ''}`, { cache: 'no-store' });
      const j = await r.json();
      setData(j);
    } catch (e) { /* noop */ } finally { setLoading(false); loadHistory(); }
  }, [loadHistory]);

  React.useEffect(() => { load(false); }, [load]);

  const text = data && data.text;
  const when = data && data.created_at;
  const past = history.filter((h) => h.created_at !== when);
  // Season timeline: weekly hit-rate across all archived weeks, oldest -> newest.
  const timeline = [...history]
    .sort((x, y) => new Date(x.created_at) - new Date(y.created_at))
    .filter((h) => h.stats && h.stats.hit_rate != null)
    .map((h, i) => ({ i: i + 1, hr: h.stats.hit_rate,
      label: h.week_label ? h.week_label.replace(/, \d+$/, '') : new Date(h.created_at).toLocaleDateString(),
      n: (h.stats && h.stats.n_graded) || 0 }));
  const avgHr = timeline.length ? Math.round(timeline.reduce((s, t) => s + t.hr, 0) / timeline.length) : null;
  const rangedTimeline = rangeW === 'all' ? timeline : timeline.slice(-Number(rangeW));
  const shownAvg = rangedTimeline.length ? Math.round(rangedTimeline.reduce((s, t) => s + t.hr, 0) / rangedTimeline.length) : null;
  const RangeBtn = ({ v, children }) => (
    <button onClick={() => setRangeW(v)} className={`rounded px-1.5 py-0.5 text-[9px] font-bold transition-colors ${String(rangeW) === String(v) ? 'bg-violet-500/20 text-violet-200 ring-1 ring-violet-500/40' : 'text-slate-500 hover:text-slate-300'}`}>{children}</button>
  );

  const keyOf = (h) => h.week_label || h.created_at;
  const isPicked = (h) => picked.some((p) => keyOf(p) === keyOf(h));
  const togglePick = (h) => {
    setPicked((prev) => {
      if (prev.some((p) => keyOf(p) === keyOf(h))) return prev.filter((p) => keyOf(p) !== keyOf(h));
      if (prev.length >= 2) return [prev[1], h]; // keep latest two picks
      return [...prev, h];
    });
  };
  const startCompare = () => { setCompareMode(true); setShowHistory(true); setPicked([]); setOpenId(null); };
  const cancelCompare = () => { setCompareMode(false); setPicked([]); };

  return (
    <div className="rounded-xl border border-slate-800 bg-gradient-to-br from-violet-950/30 to-slate-900/50 p-4">
      <div className="mb-3 flex items-center gap-2">
        <CalendarDays className="h-4 w-4 text-violet-400" />
        <h3 className="text-sm font-semibold text-white">Albert&apos;s Weekly Recap</h3>
        {when && <span className="text-[10px] text-slate-500">{new Date(when).toLocaleDateString()}</span>}
        <button onClick={() => load(true)} disabled={loading} title="Regenerate"
          className="ml-auto rounded-md p-1 text-slate-400 transition-colors hover:text-white disabled:opacity-50">
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
      {loading && !text ? (
        <p className="text-xs text-slate-500">Albert is reviewing the week…</p>
      ) : text ? (
        <div className="text-[13px] leading-relaxed text-slate-200"><AlbertText text={text} /></div>
      ) : (
        <p className="text-xs text-slate-500">Weekly recap will appear once Albert has logged some calls. Ask him a buy/sell question to get started.</p>
      )}

      {timeline.length >= 2 && (
        <div className="mt-4 border-t border-slate-800 pt-3">
          <div className="mb-1 flex items-center gap-1.5">
            <LineChartIcon className="h-3.5 w-3.5 text-violet-400" />
            <p className="text-[11px] font-semibold text-slate-300">Season hit-rate</p>
            {timeline.length > 4 && (
              <div className="ml-auto flex items-center gap-0.5">
                <RangeBtn v="4">4w</RangeBtn>
                <RangeBtn v="12">12w</RangeBtn>
                <RangeBtn v="all">All</RangeBtn>
              </div>
            )}
            {shownAvg != null && <span className={`${timeline.length > 4 ? '' : 'ml-auto'} text-[10px] text-slate-500`}>avg {shownAvg}%</span>}
          </div>
          <div className="h-28">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rangedTimeline} margin={{ top: 6, right: 8, left: -24, bottom: 0 }}>
                <XAxis dataKey="label" tick={{ fontSize: 9, fill: '#64748b' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                <YAxis domain={[0, 100]} ticks={[0, 50, 100]} tick={{ fontSize: 9, fill: '#64748b' }} axisLine={false} tickLine={false} width={30} />
                <ReferenceLine y={50} stroke="#334155" strokeDasharray="3 3" />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 11 }}
                  formatter={(v, _n, p) => [`${v}% (${(p && p.payload && p.payload.n) || 0} graded)`, 'Hit rate']}
                  labelFormatter={(l) => l} />
                <Line type="monotone" dataKey="hr" stroke="#a78bfa" strokeWidth={2} dot={{ r: 2.5 }} activeDot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {past.length > 0 && (
        <div className="mt-4 border-t border-slate-800 pt-3">
          <div className="flex items-center gap-2">
            <button onClick={() => setShowHistory((v) => !v)}
              className="flex flex-1 items-center gap-1.5 text-[11px] font-semibold text-slate-400 transition-colors hover:text-slate-200">
              <History className="h-3.5 w-3.5 text-violet-400" />
              Past recaps ({past.length})
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showHistory ? 'rotate-180' : ''}`} />
            </button>
            {past.length >= 2 && (
              compareMode ? (
                <button onClick={cancelCompare} className="flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-semibold text-slate-400 hover:text-white">
                  <X className="h-3 w-3" /> Cancel
                </button>
              ) : (
                <button onClick={startCompare} className="flex items-center gap-1 rounded-md border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[10px] font-semibold text-violet-200 hover:bg-violet-500/20">
                  <GitCompare className="h-3 w-3" /> Compare
                </button>
              )
            )}
          </div>

          {compareMode && (
            <p className="mt-2 text-[10px] text-slate-500">Pick two weeks to compare side by side ({picked.length}/2 selected).</p>
          )}

          {showHistory && (
            <div className="mt-2 max-h-72 space-y-1.5 overflow-y-auto pr-1">
              {past.map((h) => {
                const id = keyOf(h);
                const isOpen = openId === id && !compareMode;
                const hr = h.stats && h.stats.hit_rate;
                const sel = isPicked(h);
                return (
                  <div key={id} className={`rounded-lg border bg-slate-950/40 ${sel ? 'border-violet-500/60 ring-1 ring-violet-500/40' : 'border-slate-800'}`}>
                    <button onClick={() => (compareMode ? togglePick(h) : setOpenId(isOpen ? null : id))}
                      className="flex w-full items-center gap-2 px-2.5 py-2 text-left">
                      {compareMode && (
                        <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${sel ? 'border-violet-400 bg-violet-500 text-white' : 'border-slate-600'}`}>
                          {sel && <Check className="h-3 w-3" />}
                        </span>
                      )}
                      <span className="text-[12px] font-semibold text-slate-200">{h.week_label || new Date(h.created_at).toLocaleDateString()}</span>
                      {hr != null && (
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${hr >= 50 ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'}`}>{hr}% hit</span>
                      )}
                      <span className="text-[10px] text-slate-500">{new Date(h.created_at).toLocaleDateString()}</span>
                      {!compareMode && <ChevronDown className={`ml-auto h-3.5 w-3.5 text-slate-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />}
                    </button>
                    {isOpen && (
                      <div className="border-t border-slate-800 px-2.5 py-2 text-[12px] leading-relaxed text-slate-300">
                        <AlbertText text={h.text} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {compareMode && (
            <button onClick={() => setShowCompare(true)} disabled={picked.length !== 2}
              className="mt-2 w-full rounded-lg bg-violet-600 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-violet-500 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500">
              Compare selected weeks
            </button>
          )}
        </div>
      )}

      {showCompare && picked.length === 2 && (
        <CompareModal a={picked[0]} b={picked[1]} onClose={() => setShowCompare(false)} />
      )}
    </div>
  );
}

function CompareColumn({ h }) {
  const hr = h.stats && h.stats.hit_rate;
  return (
    <div className="flex-1">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-bold text-white">{h.week_label || new Date(h.created_at).toLocaleDateString()}</span>
        {hr != null && (
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${hr >= 50 ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'}`}>{hr}% hit</span>
        )}
        {h.stats && h.stats.n_graded != null && (
          <span className="text-[10px] text-slate-500">{h.stats.n_graded} graded</span>
        )}
      </div>
      <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-[12px] leading-relaxed text-slate-200">
        <AlbertText text={h.text} />
      </div>
    </div>
  );
}

function CompareModal({ a, b, onClose }) {
  // Show older week on the left, newer on the right, so it reads left-to-right in time.
  const [older, newer] = new Date(a.created_at) <= new Date(b.created_at) ? [a, b] : [b, a];
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900 p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center gap-2">
          <GitCompare className="h-4 w-4 text-violet-400" />
          <h3 className="text-sm font-bold text-white">How Albert&apos;s read shifted</h3>
          <button onClick={onClose} className="ml-auto rounded-md p-1 text-slate-400 hover:text-white"><X className="h-4 w-4" /></button>
        </div>
        <div className="flex flex-col gap-4 sm:flex-row">
          <CompareColumn h={older} />
          <div className="hidden w-px shrink-0 bg-slate-800 sm:block" />
          <CompareColumn h={newer} />
        </div>
      </div>
    </div>
  );
}
