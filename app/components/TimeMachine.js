'use client';

import React from 'react';
import { ArrowDownRight, ArrowUpRight, Check, History, Sparkles, X } from 'lucide-react';
import { ResponsiveContainer, ComposedChart, Line, LineChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, Scatter } from 'recharts';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { API_BASE } from '../lib/api';
import { fmtUsd } from '../lib/format';
import { sec } from '../lib/sections';
import { SectionHead, AiReview, ChartTooltip } from './shared';

function ScenariosPanel() {
  const [scn, setScn] = React.useState(null);
  const [sel, setSel] = React.useState(0);
  const [selB, setSelB] = React.useState(1);
  const [compare, setCompare] = React.useState(false);
  React.useEffect(() => {
    fetch(`${API_BASE}/v1/scenarios`, { cache: 'no-store' })
      .then((r) => r.json()).then((j) => { if (j.status === 'ready') setScn(j.scenarios.filter((s) => s.status === 'ready')); })
      .catch(() => {});
  }, []);
  if (!scn) return <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800"><p className="text-sm text-slate-500">Loading historic scenarios…</p></Card>;
  if (scn.length === 0) return null;
  const s = scn[sel] || scn[0];
  const win = (s.window || []).map((w) => ({ date: w.date, close: w.close, pick: w.is_pick ? w.close : null }));
  const outCol = (v) => v == null ? 'text-slate-400' : v >= 0 ? 'text-emerald-400' : 'text-red-400';
  const outTxt = (v) => v == null ? '—' : `${v >= 0 ? '+' : ''}${v}%`;

  // Rebase a scenario window to 100 at its event day, keyed by day-offset from the event
  const rebased = (scx) => {
    const w = scx.window || [];
    const pi = w.findIndex((p) => p.is_pick);
    const base = scx.price_at_event || (pi >= 0 ? w[pi].close : (w[0] && w[0].close)) || 1;
    const m = {};
    w.forEach((p, i) => { m[i - (pi < 0 ? 0 : pi)] = Math.round((p.close / base) * 1000) / 10; });
    return m;
  };
  const sB = scn[selB] || scn[(sel + 1) % scn.length];
  let overlay = [];
  if (compare) {
    const ma = rebased(s); const mb = rebased(sB);
    const offs = new Set([...Object.keys(ma), ...Object.keys(mb)].map(Number));
    overlay = Array.from(offs).filter((o) => o >= -60 && o <= 90).sort((x, y) => x - y)
      .map((o) => ({ off: o, a: ma[o] ?? null, b: mb[o] ?? null }));
  }

  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Sparkles className="h-4 w-4 text-amber-400" />
        <h3 className="text-sm font-semibold text-white">Famous Scenarios</h3>
        <span className="text-[11px] text-slate-500">point-in-time · real prices</span>
        <button onClick={() => setCompare(!compare)} className={`ml-auto rounded-full border px-3 py-1 text-xs font-semibold ${compare ? 'border-sky-400 bg-sky-500/15 text-sky-200' : 'border-slate-700 bg-slate-800/60 text-slate-300 hover:text-sky-300'}`}>{compare ? 'Comparing 2 ✓' : 'Compare two'}</button>
      </div>

      {!compare ? (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {scn.map((x, i) => (
              <button key={x.id} onClick={() => setSel(i)} className={`rounded-full border px-3 py-1.5 text-xs font-medium ${i === sel ? 'border-amber-500/40 bg-amber-500/10 text-amber-200' : 'border-slate-700 bg-slate-800/50 text-slate-400 hover:text-slate-200'}`}>{x.title}</button>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={win} margin={{ top: 10, right: 12, left: 4, bottom: 0 }}>
                    <defs><linearGradient id="scnFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#fbbf24" stopOpacity={0.25} /><stop offset="100%" stopColor="#fbbf24" stopOpacity={0} /></linearGradient></defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} minTickGap={40} />
                    <YAxis tick={{ fill: '#64748b', fontSize: 10 }} domain={['auto', 'auto']} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} width={48} />
                    <Tooltip content={<ChartTooltip />} />
                    <Area type="monotone" dataKey="close" stroke="#fbbf24" strokeWidth={2} fill="url(#scnFill)" name="BTC" />
                    <Scatter dataKey="pick" fill="#f59e0b" name="Event day" />
                    <ReferenceLine x={s.date} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: 'event', fill: '#f59e0b', fontSize: 10, position: 'top' }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wider text-amber-400">{s.category}</p>
              <h4 className="text-lg font-bold text-white">{s.title}</h4>
              <p className="text-xs text-slate-500">{s.date} · BTC {fmtUsd(s.price_at_event)}</p>
              <p className="mt-2 text-sm text-slate-400">{s.description}</p>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                {['30d', '90d', '365d'].map((k) => (
                  <div key={k} className="rounded-lg border border-slate-800 bg-slate-950/40 p-2">
                    <p className="text-[10px] uppercase text-slate-500">+{k}</p>
                    <p className={`text-sm font-bold ${outCol(s.outcomes[k])}`}>{outTxt(s.outcomes[k])}</p>
                  </div>
                ))}
              </div>
              {s.model?.available ? (
                <div className={`mt-3 rounded-lg border p-2.5 text-xs ${s.model.correct ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-300' : 'border-red-500/20 bg-red-500/5 text-red-300'}`}>
                  Model call: <span className="font-bold">{s.model.signal}</span> ({s.model.confidence}% conf) · actual {s.model.actual} · {s.model.correct ? 'correct' : 'missed'}
                </div>
              ) : (
                <p className="mt-3 rounded-lg border border-slate-800 bg-slate-950/40 p-2.5 text-[11px] text-slate-500">{s.model?.note}</p>
              )}
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wider text-amber-400">Scenario A</p>
              <select value={sel} onChange={(e) => setSel(Number(e.target.value))} className="w-full rounded-lg border border-slate-700 bg-slate-950/60 px-2 py-1.5 text-xs text-slate-200 focus:border-amber-500/50 focus:outline-none">
                {scn.map((x, i) => <option key={x.id} value={i}>{x.title} ({x.date})</option>)}
              </select>
            </div>
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wider text-sky-400">Scenario B</p>
              <select value={selB} onChange={(e) => setSelB(Number(e.target.value))} className="w-full rounded-lg border border-slate-700 bg-slate-950/60 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500/50 focus:outline-none">
                {scn.map((x, i) => <option key={x.id} value={i}>{x.title} ({x.date})</option>)}
              </select>
            </div>
          </div>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={overlay} margin={{ top: 10, right: 12, left: 4, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="off" tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}d`} />
                <YAxis tick={{ fill: '#64748b', fontSize: 10 }} domain={['auto', 'auto']} tickFormatter={(v) => `${v}`} width={40} />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }} formatter={(v, n) => [`${v} (=100 at event)`, n === 'a' ? s.title : sB.title]} labelFormatter={(l) => `${l > 0 ? '+' : ''}${l} days from event`} />
                <ReferenceLine x={0} stroke="#64748b" strokeDasharray="4 4" label={{ value: 'event', fill: '#94a3b8', fontSize: 10 }} />
                <ReferenceLine y={100} stroke="#334155" />
                <Line type="monotone" dataKey="a" stroke="#fbbf24" strokeWidth={2} dot={false} name="a" connectNulls />
                <Line type="monotone" dataKey="b" stroke="#38bdf8" strokeWidth={2} dot={false} name="b" connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex items-center justify-center gap-5 text-xs">
            <span className="flex items-center gap-1.5 text-amber-300"><span className="h-2 w-4 rounded bg-amber-400" />{s.title}</span>
            <span className="flex items-center gap-1.5 text-sky-300"><span className="h-2 w-4 rounded bg-sky-400" />{sB.title}</span>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-wider text-slate-500"><th className="pb-2">Metric</th><th className="pb-2 text-amber-300">{s.title}</th><th className="pb-2 text-sky-300">{sB.title}</th></tr></thead>
              <tbody>
                <tr className="border-t border-slate-800"><td className="py-2 text-slate-400">Event date</td><td className="py-2 text-slate-300">{s.date}</td><td className="py-2 text-slate-300">{sB.date}</td></tr>
                <tr className="border-t border-slate-800"><td className="py-2 text-slate-400">BTC at event</td><td className="py-2 text-slate-300">{fmtUsd(s.price_at_event)}</td><td className="py-2 text-slate-300">{fmtUsd(sB.price_at_event)}</td></tr>
                {['30d', '90d', '365d'].map((k) => (
                  <tr key={k} className="border-t border-slate-800">
                    <td className="py-2 text-slate-400">+{k} after</td>
                    <td className={`py-2 font-semibold ${outCol(s.outcomes[k])}`}>{outTxt(s.outcomes[k])}</td>
                    <td className={`py-2 font-semibold ${outCol(sB.outcomes[k])}`}>{outTxt(sB.outcomes[k])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p className="mt-3 text-[11px] text-slate-600">Prices are real (Yahoo/BTC-USD). In compare mode both paths are rebased to 100 at their event day so you can see how Bitcoin behaved relative to each event. Forward outcomes are revealed only after the event — never leaked into a prediction.</p>
    </Card>
  );
}

function AnalogsPanel() {
  const [d, setD] = React.useState(null);
  const [open, setOpen] = React.useState(-1);
  const [recaps, setRecaps] = React.useState({});
  const loadRecap = (a) => {
    if (recaps[a.date]) return;
    setRecaps((m) => ({ ...m, [a.date]: { loading: true } }));
    fetch(`${API_BASE}/v1/time-machine/analog-recap?date=${a.date}&price=${a.price_then}`, { cache: 'no-store' })
      .then((r) => r.json()).then((j) => setRecaps((m) => ({ ...m, [a.date]: { loading: false, text: j.recap || 'No recap available for this date.' } })))
      .catch(() => setRecaps((m) => ({ ...m, [a.date]: { loading: false, text: 'Could not load recap — please try again.' } })));
  };
  React.useEffect(() => {
    fetch(`${API_BASE}/v1/time-machine/analogs?k=3`, { cache: 'no-store' })
      .then((r) => r.json()).then(setD).catch(() => setD({ status: 'error' }));
  }, []);
  if (!d) return (<Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800"><p className="text-sm text-slate-500">Finding historical analogs (FAISS)…</p></Card>);
  if (d.status !== 'ready' || !(d.analogs || []).length) return null;

  const colors = ['#38bdf8', '#a78bfa', '#f59e0b'];
  // Build a normalized (% from day 0) forward-path chart across all analogs.
  const chart = [];
  for (let o = 0; o <= 30; o++) {
    const row = { d: o };
    d.analogs.forEach((a, i) => {
      const p0 = a.path_30d[0]?.close;
      const p = a.path_30d[o]?.close;
      if (p0 && p != null) row[`a${i}`] = +(((p - p0) / p0) * 100).toFixed(2);
    });
    chart.push(row);
  }
  const s = d.summary || {};
  const up = (s.avg_ret_30d_pct ?? 0) >= 0;

  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-white"><Sparkles className="h-4 w-4 text-violet-400" />When did this happen before?</h3>
        <span className="rounded-full border border-violet-500/40 px-2 py-0.5 text-[10px] font-bold text-violet-300">FAISS analog match</span>
        <span className="ml-auto text-[11px] text-slate-500">today ≈ {fmtUsd(d.current_price)} · as of {d.as_of}</span>
      </div>
      {s && (
        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase text-slate-500">Avg next 7d</p><p className="mt-1 text-xl font-black" style={{ color: (s.avg_ret_7d_pct ?? 0) >= 0 ? '#34d399' : '#f87171' }}>{s.avg_ret_7d_pct > 0 ? '+' : ''}{s.avg_ret_7d_pct}%</p></div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase text-slate-500">Avg next 30d</p><p className="mt-1 text-xl font-black" style={{ color: up ? '#34d399' : '#f87171' }}>{s.avg_ret_30d_pct > 0 ? '+' : ''}{s.avg_ret_30d_pct}%</p></div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase text-slate-500">Higher after 30d</p><p className="mt-1 text-xl font-black text-slate-100">{s.pct_higher_30d}%</p></div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase text-slate-500">Analogs</p><p className="mt-1 text-xl font-black text-slate-100">{d.k}</p></div>
        </div>
      )}
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chart} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="d" tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={(v) => `+${v}d`} />
            <YAxis tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={(v) => `${v}%`} width={40} />
            <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }}
              labelFormatter={(v) => `+${v} days`} formatter={(val, name) => [`${val}%`, name]} />
            <ReferenceLine y={0} stroke="#475569" strokeDasharray="2 2" />
            {d.analogs.map((a, i) => (
              <Line key={i} type="monotone" dataKey={`a${i}`} name={a.date} stroke={colors[i]} strokeWidth={2} dot={false} connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-3 space-y-1.5">
        {d.analogs.map((a, i) => (
          <div key={i} className="rounded-lg border border-slate-800/70 bg-slate-950/40">
            <button onClick={() => setOpen(open === i ? -1 : i)} className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-2.5 py-1.5 text-left text-[12px] hover:bg-slate-800/30">
              <span className="h-2 w-2 rounded-full" style={{ background: colors[i] }} />
              <span className="font-semibold text-slate-200">{a.date}</span>
              <span className="text-slate-500">{(a.similarity * 100).toFixed(1)}% match · {fmtUsd(a.price_then)}</span>
              <span className="ml-auto flex items-center gap-3">
                <span style={{ color: a.ret_7d_pct >= 0 ? '#34d399' : '#f87171' }}>7d {a.ret_7d_pct > 0 ? '+' : ''}{a.ret_7d_pct}%</span>
                <span style={{ color: a.ret_30d_pct >= 0 ? '#34d399' : '#f87171' }}>30d {a.ret_30d_pct > 0 ? '+' : ''}{a.ret_30d_pct}%</span>
                <span className={`text-slate-500 transition-transform ${open === i ? 'rotate-180' : ''}`}>▾</span>
              </span>
            </button>
            {open === i && a.context && (
              <div className="border-t border-slate-800/70 px-2.5 py-2 text-[11px] text-slate-400">
                <p className="mb-2 text-slate-300">{a.context.summary}</p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
                  <span>RSI: <b className="text-slate-200">{a.context.rsi ?? '—'}</b></span>
                  <span>Trend: <b className="text-slate-200">{a.context.trend}</b></span>
                  <span>ATR: <b className="text-slate-200">{a.context.atr_pct != null ? a.context.atr_pct + '%' : '—'}</b></span>
                  <span>Vol vs avg: <b className="text-slate-200">{a.context.volume_ratio != null ? a.context.volume_ratio + '×' : '—'}</b></span>
                  <span>Prior 7d: <b style={{ color: (a.context.prior_7d_pct ?? 0) >= 0 ? '#34d399' : '#f87171' }}>{a.context.prior_7d_pct != null ? (a.context.prior_7d_pct > 0 ? '+' : '') + a.context.prior_7d_pct + '%' : '—'}</b></span>
                  <span>Prior 30d: <b style={{ color: (a.context.prior_30d_pct ?? 0) >= 0 ? '#34d399' : '#f87171' }}>{a.context.prior_30d_pct != null ? (a.context.prior_30d_pct > 0 ? '+' : '') + a.context.prior_30d_pct + '%' : '—'}</b></span>
                </div>
                <p className="mt-2 text-[10px] italic text-slate-600">{a.context.note}</p>
                <div className="mt-2">
                  {!recaps[a.date] ? (
                    <button onClick={() => loadRecap(a)} className="rounded-md border border-violet-500/40 bg-violet-500/10 px-2 py-1 text-[10px] font-semibold text-violet-300 hover:bg-violet-500/20">Ask Albert what happened →</button>
                  ) : recaps[a.date].loading ? (
                    <p className="text-[11px] italic text-slate-500">Albert is searching the web…</p>
                  ) : (
                    <p className="rounded-md border border-slate-800 bg-slate-950/50 p-2 text-[11px] leading-snug text-slate-300"><span className="font-semibold text-violet-300">Albert: </span>{recaps[a.date].text}</p>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      <p className="mt-2 text-[10px] text-slate-600">FAISS cosine match over standardized momentum/trend/volatility/volume vectors. Click a day for its market backdrop. Past analogs are context, not a prediction — outcomes vary.</p>
    </Card>
  );
}


function TimeMachineSection() {
  const [rep, setRep] = React.useState(null);
  const [date, setDate] = React.useState('');
  const [loading, setLoading] = React.useState(true);
  const [range, setRange] = React.useState({ min: null, max: null });

  const fetchReplay = React.useCallback(async (dt) => {
    setLoading(true);
    try {
      const url = dt ? `${API_BASE}/v1/replay?date=${dt}&window=30` : `${API_BASE}/v1/replay?window=30`;
      const r = await fetch(url, { cache: 'no-store' });
      const j = await r.json();
      if (j.status === 'ready') {
        setRep(j);
        if (j.min_date && j.max_date) setRange({ min: j.min_date, max: j.max_date });
        if (!dt && j.pick_date) setDate(j.pick_date);
      }
    } catch (e) { /* noop */ }
    setLoading(false);
  }, []);

  React.useEffect(() => { fetchReplay(); }, [fetchReplay]);

  const go = () => { if (date) fetchReplay(date); };
  const shift = (days) => {
    if (!date) return;
    const d = new Date(date + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() + days);
    let nd = d.toISOString().slice(0, 10);
    if (range.min && nd < range.min) nd = range.min;
    if (range.max && nd > range.max) nd = range.max;
    setDate(nd); fetchReplay(nd);
  };

  const win = (rep && rep.window) || [];
  const chartData = win.map((w) => ({ date: w.date, close: w.close, pick: w.is_pick ? w.close : null }));
  const correct = rep && rep.correct;

  return (
    <div className="space-y-5">
      <SectionHead icon={History} title="Bitcoin Time Machine" blurb={sec('timemachine').blurb} />
      <AiReview section="timemachine" text="Albert is reviewing the Time Machine…" voice />

      <ScenariosPanel />

      <AnalogsPanel />

      <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-[11px] uppercase tracking-wider text-slate-400">Replay date</label>
            <input type="date" value={date} min={range.min || undefined} max={range.max || undefined}
              onChange={(e) => setDate(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 focus:border-sky-500/50 focus:outline-none" />
          </div>
          <Button onClick={go} disabled={loading} className="gap-1.5 bg-sky-500 hover:bg-sky-400"><History className="h-4 w-4" />Replay this day</Button>
          <div className="flex gap-1.5">
            <Button size="sm" variant="outline" onClick={() => shift(-1)} className="border-slate-700 text-slate-300 hover:bg-slate-800">◀ Prev day</Button>
            <Button size="sm" variant="outline" onClick={() => shift(1)} className="border-slate-700 text-slate-300 hover:bg-slate-800">Next day ▶</Button>
          </div>
          {range.min && <span className="ml-auto text-[11px] text-slate-500">available {range.min} → {range.max} · {rep?.n} days</span>}
        </div>
      </Card>

      {loading && !rep ? (
        <Card className="border-0 bg-slate-900 p-10 text-center ring-1 ring-slate-800"><p className="text-sm text-slate-500">Loading replay…</p></Card>
      ) : rep && rep.status === 'ready' ? (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card className={`border-0 p-5 ring-1 ${correct ? 'bg-emerald-500/5 ring-emerald-500/25' : 'bg-red-500/5 ring-red-500/25'}`}>
              <p className="text-[11px] uppercase tracking-wider text-slate-400">Model call on {rep.pick_date}</p>
              <div className="mt-2 flex items-center gap-2">
                {rep.signal === 'UP' ? <ArrowUpRight className="h-7 w-7 text-emerald-400" /> : <ArrowDownRight className="h-7 w-7 text-red-400" />}
                <span className={`text-3xl font-black ${rep.signal === 'UP' ? 'text-emerald-400' : 'text-red-400'}`}>{rep.signal}</span>
                <span className="ml-1 rounded bg-slate-800 px-2 py-0.5 text-xs font-semibold text-slate-300">{rep.confidence}% conf</span>
              </div>
              <p className="mt-2 text-xs text-slate-500">Predicted next-day direction from {fmtUsd(rep.close)}</p>
            </Card>
            <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
              <p className="text-[11px] uppercase tracking-wider text-slate-400">What actually happened</p>
              <div className="mt-2 flex items-center gap-2">
                <span className={`text-3xl font-black ${rep.actual === 'UP' ? 'text-emerald-400' : 'text-red-400'}`}>{rep.actual}</span>
                <span className={`text-lg font-bold ${rep.move_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{rep.move_pct >= 0 ? '+' : ''}{rep.move_pct}%</span>
              </div>
              <p className="mt-2 text-xs text-slate-500">{fmtUsd(rep.close)} → {fmtUsd(rep.next_close)} next day</p>
            </Card>
            <Card className={`border-0 p-5 ring-1 ${correct ? 'bg-emerald-500/5 ring-emerald-500/25' : 'bg-red-500/5 ring-red-500/25'}`}>
              <div className="flex items-center gap-1.5"><img src="/albert.png" alt="Albert" className={`h-6 w-6 rounded-full object-cover ring-1 ${correct ? 'ring-emerald-500/40' : 'ring-red-500/40'}`} onError={(e) => { e.currentTarget.style.display = 'none'; }} /><p className="text-[11px] uppercase tracking-wider text-slate-400">Albert&apos;s Call</p></div>
              <div className="mt-2 flex items-center gap-2">
                {correct ? <Check className="h-7 w-7 text-emerald-400" /> : <X className="h-7 w-7 text-red-400" />}
                <span className={`text-3xl font-black ${correct ? 'text-emerald-400' : 'text-red-400'}`}>{correct ? 'Correct' : 'Missed'}</span>
              </div>
              {rep.rolling_accuracy != null && <p className="mt-2 text-xs text-slate-500">~{rep.rolling_accuracy}% accuracy in the surrounding 30 days</p>}
            </Card>
          </div>

          <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
            <h3 className="mb-3 text-sm font-semibold text-white">Price path around {rep.pick_date}</h3>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 10, right: 12, left: 4, bottom: 0 }}>
                  <defs>
                    <linearGradient id="tmFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.28} />
                      <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} minTickGap={40} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 10 }} domain={['auto', 'auto']} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} width={48} />
                  <Tooltip content={<ChartTooltip />} />
                  <Area type="monotone" dataKey="close" stroke="#38bdf8" strokeWidth={2} fill="url(#tmFill)" name="BTC" />
                  <Scatter dataKey="pick" fill="#fbbf24" name="Replay day" />
                  {rep.pick_date && <ReferenceLine x={rep.pick_date} stroke="#fbbf24" strokeDasharray="4 4" label={{ value: 'pick', fill: '#fbbf24', fontSize: 10, position: 'top' }} />}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-[11px] text-slate-600">Highlighted point is the replay day. The model saw only data up to that day when it made the call — no future leakage.</p>
          </Card>
        </>
      ) : (
        <Card className="border-0 bg-slate-900 p-10 text-center ring-1 ring-slate-800"><p className="text-sm text-slate-500">{rep?.message || 'Replay data is still being generated — hit Retrain, then try again.'}</p></Card>
      )}
    </div>
  );
}


export default TimeMachineSection;
