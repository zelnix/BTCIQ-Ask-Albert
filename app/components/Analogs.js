'use client';

import React from 'react';
import { Bell, History } from 'lucide-react';
import { ResponsiveContainer, ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine } from 'recharts';
import { Card } from '@/components/ui/card';
import { API_BASE } from '../lib/api';
import { SymbolContext } from '../lib/context';
import { sec } from '../lib/sections';
import { SectionHead, AiReview, InfoTip, TapInfo } from './shared';

const ANALOG_CAT_COLOR = {
  Macro: 'text-amber-300 bg-amber-500/15',
  'Market structure': 'text-sky-300 bg-sky-500/15',
  'On-chain': 'text-violet-300 bg-violet-500/15',
  Events: 'text-emerald-300 bg-emerald-500/15',
};

const ANALOG_OVERLAY_COLORS = ['#f7931a', '#a855f7', '#22d3ee'];

// Interpolate a rebased forward path (list of {off,v}) at a given day; null if unresolved there.
function pathValueAt(fp, day) {
  const a = (fp || []).filter((p) => p.v != null);
  if (!a.length) return null;
  if (day <= a[0].off) return a[0].v;
  if (day > a[a.length - 1].off) return null;
  for (let i = 0; i < a.length - 1; i += 1) {
    if (a[i].off <= day && day <= a[i + 1].off) {
      const t = (day - a[i].off) / ((a[i + 1].off - a[i].off) || 1);
      return a[i].v + (a[i + 1].v - a[i].v) * t;
    }
  }
  return a[a.length - 1].v;
}

// Tiny inline win/loss forward mini-chart for each Setup History row, with hover readout.
function OutcomeSpark({ points, color }) {
  const [hover, setHover] = React.useState(null);
  const pts = (points || []).filter((p) => p.v != null);
  if (pts.length < 2) return <span className="text-slate-600">—</span>;
  const w = 92; const h = 26; const pad = 2;
  const xs = pts.map((p) => p.off); const ys = pts.map((p) => p.v);
  const minX = Math.min(...xs); const maxX = Math.max(...xs);
  const minY = Math.min(...ys, 100); const maxY = Math.max(...ys, 100);
  const sx = (x) => pad + ((x - minX) / ((maxX - minX) || 1)) * (w - 2 * pad);
  const sy = (y) => h - pad - ((y - minY) / ((maxY - minY) || 1)) * (h - 2 * pad);
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${sx(p.off).toFixed(1)},${sy(p.v).toFixed(1)}`).join(' ');
  const baseY = sy(100); const end = pts[pts.length - 1];
  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left;
    let best = 0; let bd = Infinity;
    pts.forEach((p, i) => { const dd = Math.abs(sx(p.off) - px); if (dd < bd) { bd = dd; best = i; } });
    setHover(best);
  };
  const hp = hover == null ? null : pts[hover];
  const ret = hp ? Math.round((hp.v - 100) * 10) / 10 : null;
  return (
    <span className="inline-flex items-center gap-1.5" onMouseLeave={() => setHover(null)}>
      <svg width={w} height={h} className="inline-block align-middle" onMouseMove={onMove}>
        <line x1={pad} y1={baseY} x2={w - pad} y2={baseY} stroke="#334155" strokeWidth="1" strokeDasharray="2 2" />
        <path d={d} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
        {hp && <line x1={sx(hp.off)} y1={pad} x2={sx(hp.off)} y2={h - pad} stroke={color} strokeOpacity="0.45" strokeWidth="1" />}
        <circle cx={sx(end.off)} cy={sy(end.v)} r="1.8" fill={color} />
        {hp && <circle cx={sx(hp.off)} cy={sy(hp.v)} r="2.6" fill={color} stroke="#0f172a" strokeWidth="1" />}
      </svg>
      <span className="w-[68px] text-left text-[10px] font-semibold tabular-nums leading-tight">
        {hp
          ? <span>+{hp.off}d <span className={ret >= 0 ? 'text-emerald-400' : 'text-red-400'}>{ret > 0 ? '+' : ''}{ret}%</span></span>
          : <span className="text-slate-600">hover</span>}
      </span>
    </span>
  );
}

function scoreAnalog(ep, current, norm, weights) {
  let tot = 0;
  let wsum = 0;
  Object.keys(current || {}).forEach((k) => {
    const w = weights[k] == null ? 1 : weights[k];
    const a = ep.fingerprint[k];
    const b = current[k];
    if (a == null || b == null) return;
    const std = (norm[k] && norm[k].std) || 1;
    tot += w * Math.pow((a - b) / std, 2);
    wsum += w;
  });
  if (!wsum) return 0;
  return Math.round(100 / (1 + Math.sqrt(tot / wsum)));
}

function AnalogsSection() {
  const symbol = React.useContext(SymbolContext);
  const [data, setData] = React.useState(null);
  const [status, setStatus] = React.useState('loading');
  const [weights, setWeights] = React.useState({});
  const [threshold, setThreshold] = React.useState(70);
  const [overlayCount, setOverlayCount] = React.useState(2);
  const [showBand, setShowBand] = React.useState(true);
  const [histThreshold, setHistThreshold] = React.useState(55);
  const [readoutHorizon, setReadoutHorizon] = React.useState(90);
  const [showModel, setShowModel] = React.useState(true);
  const [fcPath, setFcPath] = React.useState(null);

  // Today's own model forecast (BitMarkAI base scenario) rebased to 100 at now, so it can be
  // overlaid against the historical median path.
  React.useEffect(() => {
    let alive = true;
    setFcPath(null);
    const url = symbol === 'BTC' ? `${API_BASE}/v1/dashboard` : `${API_BASE}/v1/dashboard?symbol=${encodeURIComponent(symbol)}`;
    fetch(url, { cache: 'no-store' }).then((r) => r.json()).then((j) => {
      if (!alive || j.status !== 'ready') return;
      const bm = j.bitmark || {};
      const cp = bm.current_price || j.last_close;
      if (!cp || !bm.horizons) return;
      const map = { '1W': 7, '1M': 30, '3M': 90, '6M': 180 };
      const anchors = [{ off: 0, v: 100 }];
      (bm.horizons || []).forEach((h) => {
        const off = map[h.horizon];
        if (off == null || h.type !== 'model' || h.base_low == null || h.base_high == null) return;
        const mid = (h.base_low + h.base_high) / 2;
        anchors.push({ off, v: Math.round((mid / cp) * 1000) / 10 });
      });
      anchors.sort((a, b) => a.off - b.off);
      if (anchors.length > 1) setFcPath(anchors);
    }).catch(() => { /* noop */ });
    return () => { alive = false; };
  }, [symbol]);

  React.useEffect(() => {
    try { const t = parseInt(localStorage.getItem('analog_threshold'), 10); if (t) setThreshold(t); } catch (e) { /* noop */ }
    try { const h = parseInt(localStorage.getItem('analog_hist_threshold'), 10); if (h) setHistThreshold(h); } catch (e) { /* noop */ }
  }, []);
  React.useEffect(() => { try { localStorage.setItem('analog_threshold', String(threshold)); } catch (e) { /* noop */ } }, [threshold]);
  React.useEffect(() => { try { localStorage.setItem('analog_hist_threshold', String(histThreshold)); } catch (e) { /* noop */ } }, [histThreshold]);

  React.useEffect(() => {
    let alive = true;
    setStatus('loading'); setData(null); setWeights({});
    const load = () => fetch(`${API_BASE}/v1/analogs?symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store' }).then((r) => r.json()).then((j) => {
      if (!alive) return;
      if (j.status === 'ready') {
        setData(j);
        setStatus('ready');
        setWeights((w) => (Object.keys(w).length ? w : Object.fromEntries((j.signals || []).map((s) => [s.key, 1]))));
      } else if (j.status === 'error') { setStatus('error'); } else { setStatus('computing'); }
    }).catch(() => { if (alive) setStatus('error'); });
    load();
    const id = setInterval(() => setStatus((s) => { if (s !== 'ready') load(); return s; }), 5000);
    return () => { alive = false; clearInterval(id); };
  }, [symbol]);

  const ranked = React.useMemo(() => {
    if (!data) return [];
    return data.episodes.map((e) => ({ ...e, match: scoreAnalog(e, data.current, data.norm, weights) })).sort((a, b) => b.match - a.match);
  }, [data, weights]);

  const topEp = ranked[0];
  const overlayEps = React.useMemo(() => ranked.slice(0, overlayCount), [ranked, overlayCount]);
  const overlay = React.useMemo(() => {
    if (!data || !overlayEps.length) return [];
    const cur = Object.fromEntries((data.current_path || []).map((p) => [p.off, p.v]));
    const maps = overlayEps.map((ep) => Object.fromEntries((ep.path || []).map((p) => [p.off, p.v])));
    const offsSet = new Set(Object.keys(cur).map(Number));
    maps.forEach((m) => Object.keys(m).forEach((o) => offsSet.add(Number(o))));
    const offs = Array.from(offsSet).sort((a, b) => a - b);
    return offs.map((o) => {
      const row = { off: o, Today: cur[o] == null ? null : cur[o] };
      maps.forEach((m, idx) => { row[`A${idx}`] = m[o] == null ? null : m[o]; });
      return row;
    });
  }, [data, overlayEps]);

  // Setup History — score every past resolved day against today's setup (respecting live slider
  // weights), keep all above the alert threshold, dedupe nearby clusters, and grade each outcome.
  const setupHistory = React.useMemo(() => {
    if (!data || !data.day_fingerprints) return { rows: [], stats: null };
    const scored = data.day_fingerprints
      .map((d) => ({ ...d, match: scoreAnalog({ fingerprint: d.fp }, data.current, data.norm, weights) }))
      .filter((d) => d.match >= histThreshold)
      .sort((a, b) => (a.date < b.date ? -1 : 1));
    const filtered = [];
    scored.forEach((d) => {
      const last = filtered[filtered.length - 1];
      if (last && Math.abs(new Date(d.date) - new Date(last.date)) < 21 * 864e5) {
        if (d.match > last.match) filtered[filtered.length - 1] = d;
      } else filtered.push(d);
    });
    const resolved = filtered.filter((d) => d.fwd_90 != null);
    const wins = resolved.filter((d) => d.fwd_90 > 0);
    const avg = (arr) => { const a = arr.filter((v) => v != null); return a.length ? Math.round((a.reduce((s, v) => s + v, 0) / a.length) * 10) / 10 : null; };
    const stats = {
      n: filtered.length,
      nResolved: resolved.length,
      winRate: resolved.length ? Math.round((wins.length / resolved.length) * 100) : null,
      avg30: avg(resolved.map((d) => d.fwd_30)),
      avg90: avg(resolved.map((d) => d.fwd_90)),
      avg180: avg(resolved.map((d) => d.fwd_180)),
    };
    return { rows: filtered.slice().sort((a, b) => b.match - a.match), stats };
  }, [data, weights, histThreshold]);

  // Analog Confidence Band — across all matching Setup-History days, gather each day's rebased
  // forward path and compute per-offset percentiles (p10/p25/median/p75/p90). This shades the
  // spread of past outcomes around the overlay so you can see the range at a glance.
  const band = React.useMemo(() => {
    const rows = setupHistory.rows || [];
    if (!showBand || rows.length < 4) return { byOff: {}, color: '#38bdf8', n: rows.length, finalMed: null };
    const pct = (arr, p) => {
      if (!arr.length) return null;
      const s = arr.slice().sort((a, b) => a - b);
      const idx = (s.length - 1) * p;
      const lo = Math.floor(idx); const hi = Math.ceil(idx);
      return lo === hi ? s[lo] : s[lo] + (s[hi] - s[lo]) * (idx - lo);
    };
    const offSet = new Set();
    rows.forEach((r) => (r.fwd_path || []).forEach((p) => { if (p.v != null) offSet.add(p.off); }));
    const byOff = {};
    Array.from(offSet).forEach((off) => {
      const vals = [];
      rows.forEach((r) => { const p = (r.fwd_path || []).find((x) => x.off === off); if (p && p.v != null) vals.push(p.v); });
      if (vals.length < 4) return;
      byOff[off] = { b10: pct(vals, 0.1), b25: pct(vals, 0.25), b50: pct(vals, 0.5), b75: pct(vals, 0.75), b90: pct(vals, 0.9), n: vals.length };
    });
    const offs = Object.keys(byOff).map(Number).sort((a, b) => a - b);
    const finalMed = offs.length ? byOff[offs[offs.length - 1]].b50 : null;
    const color = finalMed == null ? '#38bdf8' : finalMed >= 100 ? '#10b981' : '#f43f5e';
    const atDay = (day) => {
      if (!offs.length) return null;
      if (byOff[day]) return byOff[day];
      if (day < offs[0] || day > offs[offs.length - 1]) return null;
      let lo = offs[0]; let hi = offs[offs.length - 1];
      for (let i = 0; i < offs.length - 1; i += 1) { if (offs[i] <= day && day <= offs[i + 1]) { lo = offs[i]; hi = offs[i + 1]; break; } }
      const a = byOff[lo]; const b = byOff[hi]; const t = (day - lo) / ((hi - lo) || 1);
      const mix = (x, y) => x + (y - x) * t;
      return { b25: mix(a.b25, b.b25), b50: mix(a.b50, b.b50), b75: mix(a.b75, b.b75) };
    };
    const r90 = atDay(90);
    const mkReadout = (day) => { const r = atDay(day); return r ? { lo: Math.round((r.b25 - 100) * 10) / 10, med: Math.round((r.b50 - 100) * 10) / 10, hi: Math.round((r.b75 - 100) * 10) / 10 } : null; };
    const readouts = { 30: mkReadout(30), 90: mkReadout(90), 180: mkReadout(180) };
    const readout = r90 ? { lo: Math.round((r90.b25 - 100) * 10) / 10, med: Math.round((r90.b50 - 100) * 10) / 10, hi: Math.round((r90.b75 - 100) * 10) / 10 } : null;
    return { byOff, color, n: rows.length, finalMed, readout, readouts };
  }, [setupHistory, showBand]);

  // Merge the overlay analog paths with the confidence-band stack fields for the ComposedChart.
  // Band percentiles are stored on a coarse grid (every 12d); we linearly interpolate them onto
  // every chart offset so the stacked areas render as a smooth, gap-free band.
  const chartData = React.useMemo(() => {
    const offs = Object.keys(band.byOff).map(Number).sort((a, b) => a - b);
    const minOff = offs[0]; const maxOff = offs[offs.length - 1];
    const interp = (off) => {
      if (!offs.length || off < minOff || off > maxOff) return null;
      if (band.byOff[off]) return band.byOff[off];
      let lo = offs[0]; let hi = offs[offs.length - 1];
      for (let i = 0; i < offs.length - 1; i += 1) { if (offs[i] <= off && off <= offs[i + 1]) { lo = offs[i]; hi = offs[i + 1]; break; } }
      const a = band.byOff[lo]; const b = band.byOff[hi]; const t = (off - lo) / (hi - lo || 1);
      const mix = (x, y) => x + (y - x) * t;
      return { b10: mix(a.b10, b.b10), b25: mix(a.b25, b.b25), b50: mix(a.b50, b.b50), b75: mix(a.b75, b.b75), b90: mix(a.b90, b.b90) };
    };
    const fcInterp = (off) => {
      if (!showModel || !fcPath || off < 0) return null;
      const a = fcPath;
      if (off < a[0].off || off > a[a.length - 1].off) return null;
      for (let i = 0; i < a.length - 1; i += 1) { if (a[i].off <= off && off <= a[i + 1].off) { const t = (off - a[i].off) / ((a[i + 1].off - a[i].off) || 1); return a[i].v + (a[i + 1].v - a[i].v) * t; } }
      return a[a.length - 1].v;
    };
    return overlay.map((row) => {
      const fc = fcInterp(row.off);
      const withFc = { modelFc: fc == null ? null : Math.round(fc * 10) / 10 };
      const b = interp(row.off);
      if (!b) return { ...row, ...withFc, bandBase: null, bandR1: null, bandR2: null, bandR3: null, bandMed: null };
      return {
        ...row,
        ...withFc,
        bandBase: Math.round(b.b10 * 10) / 10,
        bandR1: Math.round((b.b25 - b.b10) * 10) / 10,
        bandR2: Math.round((b.b75 - b.b25) * 10) / 10,
        bandR3: Math.round((b.b90 - b.b75) * 10) / 10,
        bandMed: Math.round(b.b50 * 10) / 10,
      };
    });
  }, [overlay, band, fcPath, showModel]);
  const bandActive = showBand && Object.keys(band.byOff).length > 0;
  const modelActive = showModel && !!fcPath;

  // Model vs History verdicts — where today's model projection sits within the distribution of
  // past look-alike outcomes at 30 / 90 / 180 days (shown as at-a-glance chips).
  const verdicts = React.useMemo(() => {
    const rows = (setupHistory.rows || []);
    if (!fcPath || rows.length < 4) return [];
    return [30, 90, 180].map((H) => {
      const mv = pathValueAt(fcPath, H);
      if (mv == null) return { H, ok: false };
      const outs = [];
      rows.forEach((r) => { const v = pathValueAt(r.fwd_path, H); if (v != null) outs.push(v); });
      if (outs.length < 4) return { H, ok: false };
      const below = outs.filter((v) => v < mv).length;
      return { H, ok: true, pctBelow: Math.round((below / outs.length) * 100), n: outs.length, modelRet: Math.round((mv - 100) * 10) / 10 };
    });
  }, [fcPath, setupHistory]);

  const sig = (k) => (data ? data.signals.find((s) => s.key === k) : null);
  const fmtSig = (k, v) => {
    if (v == null) return '—';
    const u = sig(k) ? sig(k).unit : '';
    return `${v}${u ? (u === '%' || u === 'pts' || u === 'mo' ? u : ` ${u}`) : ''}`;
  };
  const retColor = (v) => (v == null ? 'text-slate-500' : v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300');
  const closeness = (ep, k) => {
    if (!data) return 2;
    const a = ep.fingerprint[k];
    const b = data.current[k];
    if (a == null || b == null) return null;
    const std = (data.norm[k] && data.norm[k].std) || 1;
    const z = Math.abs((a - b) / std);
    return z < 0.5 ? 0 : z < 1.2 ? 1 : 2;
  };

  return (
    <div className="space-y-6">
      <SectionHead icon={History} title="Happening Again" blurb={sec('analogs').blurb} coin={symbol} />
      <AiReview text={data ? `Today's ${symbol} setup most resembles ${(ranked[0] || {}).label || 'a past episode'} (${(ranked[0] || {}).match || '—'}% match).` : 'Scanning history for the closest analog…'} voice section="analogs" />

      {status === 'ready' && topEp && topEp.match >= threshold && (
        <Card className="border-0 bg-gradient-to-r from-amber-500/15 to-sky-500/10 p-4 ring-1 ring-amber-500/40 animate-in fade-in-0 slide-in-from-top-1 duration-300">
          <div className="flex items-start gap-3">
            <span className="relative mt-0.5 flex h-6 w-6 items-center justify-center">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400/40" />
              <Bell className="relative h-5 w-5 text-amber-300" />
            </span>
            <div className="text-sm">
              <p className="font-bold text-white">Strong setup forming — {topEp.match}% match to {topEp.label}</p>
              <p className="text-slate-300">Back then, {symbol} went on to move <b className={topEp.fwd_90 >= 0 ? 'text-emerald-400' : 'text-red-400'}>{topEp.fwd_90 == null ? '—' : `${topEp.fwd_90 > 0 ? '+' : ''}${topEp.fwd_90}%`}</b> over the next 90 days. Educational pattern-match, not a prediction. <span className="text-slate-500">(A daily bell alert fires automatically at ≥70%.)</span></p>
            </div>
          </div>
        </Card>
      )}

      {status !== 'ready' || !data ? (
        <Card className="border-0 bg-slate-900/60 p-10 text-center ring-1 ring-slate-800">
          <p className="text-sm text-slate-400">{status === 'error' ? 'Could not load the analog engine. Retrying…' : `Scanning ${symbol} history and building fingerprints…`}</p>
        </Card>
      ) : (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="border-0 bg-slate-900/60 p-5 ring-1 ring-slate-800">
              <h3 className="mb-3 text-sm font-bold text-white">Today&apos;s {symbol} setup <span className="text-[11px] font-normal text-slate-500">(as of {data.as_of})</span></h3>
              <div className="space-y-2">
                {data.signals.map((s) => (
                  <div key={s.key} className="flex items-center justify-between gap-2 text-sm">
                    <span className="flex items-center gap-2 text-slate-300">
                      <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${ANALOG_CAT_COLOR[s.cat] || 'bg-slate-700 text-slate-300'}`}>{s.cat}</span>
                      {s.label}
                    </span>
                    <span className="font-semibold text-white">{fmtSig(s.key, data.current[s.key])}</span>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="border-0 bg-slate-900/60 p-5 ring-1 ring-slate-800">
              <div className="mb-3 flex items-center justify-between">
                <TapInfo text="Drag a slider up to make that signal count more when matching today to the past, or down to ignore it. The ranking below updates instantly.">
                  <h3 className="pr-5 text-sm font-bold text-white">Tune what matters</h3>
                </TapInfo>
                <button onClick={() => setWeights(Object.fromEntries(data.signals.map((s) => [s.key, 1])))} className="text-[11px] text-sky-400 hover:text-sky-300">Reset</button>
              </div>
              <div className="space-y-2.5">
                {data.signals.map((s) => (
                  <div key={s.key} className="flex items-center gap-3">
                    <span className="w-40 shrink-0 truncate text-xs text-slate-400">{s.label}</span>
                    <input type="range" min="0" max="3" step="0.5" value={weights[s.key] == null ? 1 : weights[s.key]}
                      onChange={(e) => setWeights((w) => ({ ...w, [s.key]: parseFloat(e.target.value) }))}
                      className="h-1.5 flex-1 cursor-pointer accent-sky-400" />
                    <span className="w-8 shrink-0 text-right text-xs font-semibold text-slate-300">{(weights[s.key] == null ? 1 : weights[s.key]).toFixed(1)}×</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <Card className="border-0 bg-slate-900/60 p-5 ring-1 ring-slate-800">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <TapInfo text="Overlays the top past episodes' price paths (each rebased to 100 at its own setup point) with Bitcoin's recent path (rebased to 100 at today). Left of 0 shows how similar the lead-ins are; each analog line right of 0 shows what happened next.">
                <h3 className="pr-5 text-sm font-bold text-white">Shape overlay · today vs top {overlayCount} analogs</h3>
              </TapInfo>
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-1 text-[11px] text-slate-400">
                  <span>Overlay</span>
                  {[2, 3].map((n) => (
                    <button key={n} onClick={() => setOverlayCount(n)}
                      className={`rounded px-2 py-0.5 text-[11px] font-semibold transition ${overlayCount === n ? 'bg-sky-500/25 text-sky-300 ring-1 ring-sky-500/40' : 'bg-slate-800 text-slate-400 hover:text-slate-200'}`}>
                      Top {n}
                    </button>
                  ))}
                </div>
                <button onClick={() => setShowBand((v) => !v)}
                  className={`rounded px-2 py-0.5 text-[11px] font-semibold transition ${showBand ? 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40' : 'bg-slate-800 text-slate-400 hover:text-slate-200'}`}>
                  Outcome band {showBand ? 'on' : 'off'}
                </button>
                <button onClick={() => setShowModel((v) => !v)} disabled={!fcPath}
                  className={`rounded px-2 py-0.5 text-[11px] font-semibold transition disabled:opacity-40 ${showModel ? 'bg-white/15 text-slate-100 ring-1 ring-white/30' : 'bg-slate-800 text-slate-400 hover:text-slate-200'}`}>
                  Model forecast {showModel ? 'on' : 'off'}
                </button>
                <div className="flex items-center gap-2 text-[11px] text-slate-400">
                  <Bell className="h-3.5 w-3.5 text-amber-300" />
                  <span>Alert me at ≥</span>
                  <input type="range" min="50" max="90" step="5" value={threshold} onChange={(e) => setThreshold(parseInt(e.target.value, 10))} className="h-1.5 w-24 cursor-pointer accent-amber-400" />
                  <span className="w-8 font-semibold text-amber-300">{threshold}%</span>
                </div>
              </div>
            </div>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 6, right: 12, left: -14, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="off" type="number" domain={['dataMin', 'dataMax']} stroke="#64748b" fontSize={11} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}d`} />
                  <YAxis stroke="#64748b" fontSize={11} domain={['auto', 'auto']} tickFormatter={(v) => Math.round(v)} />
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} labelFormatter={(v) => `${v > 0 ? '+' : ''}${v} days from setup`} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <ReferenceLine x={0} stroke="#64748b" strokeDasharray="4 4" />
                  <ReferenceLine y={100} stroke="#334155" strokeDasharray="3 3" />
                  {bandActive && <Area dataKey="bandBase" stackId="band" stroke="none" fill="transparent" connectNulls isAnimationActive={false} legendType="none" tooltipType="none" activeDot={false} />}
                  {bandActive && <Area dataKey="bandR1" stackId="band" stroke="none" fill={band.color} fillOpacity={0.08} connectNulls isAnimationActive={false} name="Past range (10–90%)" activeDot={false} />}
                  {bandActive && <Area dataKey="bandR2" stackId="band" stroke="none" fill={band.color} fillOpacity={0.2} connectNulls isAnimationActive={false} name="Middle 50% of outcomes" activeDot={false} />}
                  {bandActive && <Area dataKey="bandR3" stackId="band" stroke="none" fill={band.color} fillOpacity={0.08} connectNulls isAnimationActive={false} legendType="none" tooltipType="none" activeDot={false} />}
                  {bandActive && <Line type="monotone" dataKey="bandMed" stroke={band.color} strokeWidth={1.6} strokeDasharray="5 4" dot={false} connectNulls name="Median past outcome" />}
                  {overlayEps.map((ep, idx) => (
                    <Line key={ep.id} type="monotone" dataKey={`A${idx}`} stroke={ANALOG_OVERLAY_COLORS[idx % ANALOG_OVERLAY_COLORS.length]} strokeWidth={2} dot={false} connectNulls name={`${ep.label} (${ep.match}%)`} />
                  ))}
                  {modelActive && <Line type="monotone" dataKey="modelFc" stroke="#f8fafc" strokeWidth={2} strokeDasharray="2 3" dot={false} connectNulls name="Today’s model (base)" />}
                  <Line type="monotone" dataKey="Today" stroke="#38bdf8" strokeWidth={2.6} dot={false} connectNulls name={`${symbol} now`} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-[11px] text-slate-500">
              Each line is rebased to 100 at its own “now / setup” point (day 0). Left of 0 = the lead-in shapes; right of 0 = how each analog played out afterward.
              {bandActive
                ? <> The shaded {band.color === '#10b981' ? 'green' : band.color === '#f43f5e' ? 'red' : ''} band shows the spread of ALL {band.n} matching past setups: the darker core is the middle 50% of outcomes, the lighter halo the 10–90% range, and the dashed line the median path.</>
                : <> Turn on “Outcome band” to shade the range of every past matching setup around these paths.</>}
              {modelActive && <> The white dotted line is Ask Albert’s own base-case forecast for today — see where the model sits versus what history did.</>}
            </p>
            {bandActive && (
              <div className="mt-2 rounded-lg bg-slate-950/50 px-3 py-2 text-xs text-slate-300 ring-1 ring-slate-800">
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <span className="font-semibold text-white">In plain English</span>
                  <div className="flex items-center gap-1 text-[11px] text-slate-400">
                    <span>at</span>
                    {[30, 90, 180].map((hz) => (
                      <button key={hz} onClick={() => setReadoutHorizon(hz)}
                        className={`rounded px-1.5 py-0.5 font-semibold transition ${readoutHorizon === hz ? 'bg-sky-500/25 text-sky-300 ring-1 ring-sky-500/40' : 'bg-slate-800 text-slate-400 hover:text-slate-200'}`}>
                        {hz}d
                      </button>
                    ))}
                  </div>
                </div>
                {band.readouts[readoutHorizon] ? (
                  <p>
                    Across the {band.n} past setups like today, the middle 50% landed between{' '}
                    <b className={band.readouts[readoutHorizon].lo >= 0 ? 'text-emerald-400' : 'text-red-400'}>{band.readouts[readoutHorizon].lo > 0 ? '+' : ''}{band.readouts[readoutHorizon].lo}%</b> and{' '}
                    <b className={band.readouts[readoutHorizon].hi >= 0 ? 'text-emerald-400' : 'text-red-400'}>{band.readouts[readoutHorizon].hi > 0 ? '+' : ''}{band.readouts[readoutHorizon].hi}%</b> at {readoutHorizon} days (median{' '}
                    <b className={band.readouts[readoutHorizon].med >= 0 ? 'text-emerald-400' : 'text-red-400'}>{band.readouts[readoutHorizon].med > 0 ? '+' : ''}{band.readouts[readoutHorizon].med}%</b>).
                  </p>
                ) : (
                  <p className="text-slate-500">Not enough resolved history at {readoutHorizon} days for this setup — try a shorter horizon or a looser match level.</p>
                )}
                {modelActive && verdicts.length > 0 && (
                  <div className="mt-2 border-t border-slate-800 pt-2">
                    <span className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold text-white">
                      Model vs history
                      <InfoTip below={false} text="For each horizon we take Ask Albert's own base-case price, rebase it to 100 like the chart, and rank it against the matching past setups' actual outcomes at that horizon. “bearish X%” means the model projects a lower result than X% of those look-alikes; “bullish X%” means higher than X% of them." />
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {verdicts.map((v) => (v.ok ? (
                        <div key={v.H} className="flex items-center gap-1.5 rounded-lg bg-slate-900/80 px-2.5 py-1 ring-1 ring-slate-800">
                          <span className="text-[11px] font-bold text-slate-400">{v.H}d</span>
                          <span className={`text-[11px] font-semibold ${v.modelRet >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{v.modelRet > 0 ? '+' : ''}{v.modelRet}%</span>
                          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${v.pctBelow >= 50 ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'}`}>
                            {v.pctBelow >= 50 ? `bullish ${v.pctBelow}%` : `bearish ${100 - v.pctBelow}%`}
                          </span>
                        </div>
                      ) : (
                        <div key={v.H} className="flex items-center gap-1.5 rounded-lg bg-slate-900/50 px-2.5 py-1 text-[11px] text-slate-600 ring-1 ring-slate-800">{v.H}d · n/a</div>
                      )))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>

          <Card className="border-0 bg-slate-900/60 p-5 ring-1 ring-slate-800">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <TapInfo text="A backtest of today's setup: every past day whose conditions matched today (at or above the match level below, using the same slider weights) is listed here with what Bitcoin did next. The win rate is the share of those days that were higher 90 days later.">
                <h3 className="pr-5 text-sm font-bold text-white">Setup history · when this happened before</h3>
              </TapInfo>
              <div className="flex items-center gap-2 text-[11px] text-slate-400">
                <span>Match ≥</span>
                <input type="range" min="40" max="80" step="5" value={histThreshold} onChange={(e) => setHistThreshold(parseInt(e.target.value, 10))} className="h-1.5 w-24 cursor-pointer accent-sky-400" />
                <span className="w-8 font-semibold text-sky-300">{histThreshold}%</span>
              </div>
            </div>
            {setupHistory.rows.length === 0 ? (
              <p className="py-6 text-center text-sm text-slate-500">No past days reach the {histThreshold}% match level. Lower the “Match ≥” level or ease the slider weights to surface looser analogs.</p>
            ) : (
              <>
                <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="rounded-lg bg-slate-950/50 p-3 text-center">
                    <p className="text-2xl font-black text-white">{setupHistory.stats.n}</p>
                    <p className="text-[9px] uppercase tracking-wider text-slate-500">matching days</p>
                  </div>
                  <div className="rounded-lg bg-slate-950/50 p-3 text-center">
                    <p className="text-2xl font-black" style={{ color: setupHistory.stats.winRate == null ? '#94a3b8' : setupHistory.stats.winRate >= 50 ? '#34d399' : '#f87171' }}>{setupHistory.stats.winRate == null ? '—' : `${setupHistory.stats.winRate}%`}</p>
                    <p className="text-[9px] uppercase tracking-wider text-slate-500">higher after 90d</p>
                  </div>
                  <div className="rounded-lg bg-slate-950/50 p-3 text-center">
                    <p className={`text-2xl font-black ${retColor(setupHistory.stats.avg90)}`}>{setupHistory.stats.avg90 == null ? '—' : `${setupHistory.stats.avg90 > 0 ? '+' : ''}${setupHistory.stats.avg90}%`}</p>
                    <p className="text-[9px] uppercase tracking-wider text-slate-500">avg 90d move</p>
                  </div>
                  <div className="rounded-lg bg-slate-950/50 p-3 text-center">
                    <p className={`text-2xl font-black ${retColor(setupHistory.stats.avg180)}`}>{setupHistory.stats.avg180 == null ? '—' : `${setupHistory.stats.avg180 > 0 ? '+' : ''}${setupHistory.stats.avg180}%`}</p>
                    <p className="text-[9px] uppercase tracking-wider text-slate-500">avg 180d move</p>
                  </div>
                </div>
                <div className="max-h-72 overflow-y-auto rounded-lg ring-1 ring-slate-800">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-slate-900/95 text-[10px] uppercase tracking-wider text-slate-500">
                      <tr>
                        <th className="px-3 py-2 text-left font-semibold">Date</th>
                        <th className="px-3 py-2 text-right font-semibold">Match</th>
                        <th className="px-3 py-2 text-center font-semibold">Path (0→180d)</th>
                        <th className="px-3 py-2 text-right font-semibold">+30d</th>
                        <th className="px-3 py-2 text-right font-semibold">+90d</th>
                        <th className="px-3 py-2 text-right font-semibold">+180d</th>
                        <th className="px-3 py-2 text-right font-semibold">Outcome</th>
                      </tr>
                    </thead>
                    <tbody>
                      {setupHistory.rows.map((r) => {
                        const win = r.fwd_90 == null ? null : r.fwd_90 > 0;
                        return (
                          <tr key={r.date} className="border-t border-slate-800/70">
                            <td className="px-3 py-2 text-slate-300">{r.date}</td>
                            <td className="px-3 py-2 text-right font-semibold" style={{ color: r.match >= 80 ? '#34d399' : r.match >= 70 ? '#38bdf8' : '#94a3b8' }}>{r.match}%</td>
                            <td className="px-3 py-2 text-center"><OutcomeSpark points={r.fwd_path} color={win == null ? '#64748b' : win ? '#34d399' : '#f87171'} /></td>
                            <td className={`px-3 py-2 text-right ${retColor(r.fwd_30)}`}>{r.fwd_30 == null ? '—' : `${r.fwd_30 > 0 ? '+' : ''}${r.fwd_30}%`}</td>
                            <td className={`px-3 py-2 text-right ${retColor(r.fwd_90)}`}>{r.fwd_90 == null ? '—' : `${r.fwd_90 > 0 ? '+' : ''}${r.fwd_90}%`}</td>
                            <td className={`px-3 py-2 text-right ${retColor(r.fwd_180)}`}>{r.fwd_180 == null ? '—' : `${r.fwd_180 > 0 ? '+' : ''}${r.fwd_180}%`}</td>
                            <td className="px-3 py-2 text-right">
                              {win == null ? <span className="text-slate-500">open</span>
                                : <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${win ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'}`}>{win ? 'WIN' : 'LOSS'}</span>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <p className="mt-3 text-[11px] italic text-slate-500">“Win” = Bitcoin was higher 90 days later. Sampled from ~10 years of daily data (a small sample) and de-duplicated so clustered days count once. Educational pattern-matching, not a prediction or financial advice.</p>
              </>
            )}
          </Card>

          <div>
            <h3 className="mb-3 text-sm font-bold text-white">Closest historical analogs</h3>
            <div className="grid gap-4 md:grid-cols-2">
              {ranked.slice(0, 6).map((ep) => {
                const up = ep.type === 'rally';
                return (
                  <Card key={ep.id} className="border-0 bg-slate-900/60 p-4 ring-1 ring-slate-800">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="flex items-center gap-2 font-bold text-white">
                          <span className={up ? 'text-emerald-400' : 'text-red-400'}>{up ? '▲' : '▼'}</span>{ep.label}
                        </p>
                        <p className="text-[11px] text-slate-500">{ep.start} → {ep.end} · {ep.duration_days}d</p>
                      </div>
                      <div className="text-right">
                        <p className="text-2xl font-black" style={{ color: ep.match >= 70 ? '#34d399' : ep.match >= 50 ? '#38bdf8' : '#94a3b8' }}>{ep.match}%</p>
                        <p className="text-[9px] uppercase tracking-wider text-slate-500">match</p>
                      </div>
                    </div>

                    {ep.tags && ep.tags.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {ep.tags.map((t, i) => (
                          <span key={i} className={`rounded px-1.5 py-0.5 text-[9px] font-semibold ${ANALOG_CAT_COLOR[t.cat] || 'bg-slate-700 text-slate-300'}`}>{t.label}</span>
                        ))}
                      </div>
                    )}

                    <div className="mt-3 grid grid-cols-3 gap-2 rounded-lg bg-slate-950/50 p-2 text-center">
                      {[['30d', ep.fwd_30], ['90d', ep.fwd_90], ['180d', ep.fwd_180]].map(([lbl, v]) => (
                        <div key={lbl}>
                          <p className="text-[9px] uppercase text-slate-500">then +{lbl}</p>
                          <p className={`text-sm font-bold ${retColor(v)}`}>{v == null ? '—' : `${v > 0 ? '+' : ''}${v}%`}</p>
                        </div>
                      ))}
                    </div>

                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {data.signals.map((s) => {
                        const c = closeness(ep, s.key);
                        const col = c === 0 ? 'bg-emerald-500/20 text-emerald-300' : c === 1 ? 'bg-amber-500/20 text-amber-300' : 'bg-red-500/15 text-red-300';
                        return <span key={s.key} title={`${s.label}: then ${fmtSig(s.key, ep.fingerprint[s.key])} vs now ${fmtSig(s.key, data.current[s.key])}`} className={`rounded px-1.5 py-0.5 text-[9px] font-medium ${col}`}>{s.label.split(' ')[0]}{c === 0 ? ' ✓' : ''}</span>;
                      })}
                    </div>
                  </Card>
                );
              })}
            </div>
            <p className="mt-3 text-[11px] italic text-slate-500">Green = that condition closely matches today; amber = somewhat; red = quite different. Based on ~10 years of data — a small sample. Educational pattern-matching, not a prediction or financial advice.</p>
          </div>
        </>
      )}
    </div>
  );
}


export default AnalogsSection;
