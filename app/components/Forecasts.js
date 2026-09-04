'use client';

import React from 'react';
import { Check, Newspaper, Target, TrendingDown, TrendingUp, X, RefreshCw, Sparkles } from 'lucide-react';
import { ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { API_BASE, getPid } from '../lib/api';
import { fmtUsd, f24, fBy, DIR_COLOR } from '../lib/format';
import { SymbolContext } from '../lib/context';
import { sec, SECTIONS } from '../lib/sections';
import { SectionHead, AiReview, InfoTip } from './shared';

function reviewForecasts(d) {
  const a = fBy(d, '24H'), b = fBy(d, '7D'), c = fBy(d, '30D');
  if (!a || !b || !c) return 'Forecasts are still being generated.';
  const best = [a, b, c].sort((x, y) => y.confidence_pct - x.confidence_pct)[0];
  return `The near-term (24h) picture is ${a.higher >= a.lower ? 'mildly constructive' : 'cautious'} at ${a.higher}% higher, while the 30-day view leans ${c.higher >= c.lower ? 'up' : 'down'} (${Math.max(c.higher, c.lower)}% ${c.higher >= c.lower ? 'higher' : 'lower'}). The engine is most confident on the ${best.horizon} horizon (${best.confidence} · ~${best.accuracy}% historical hit-rate). Treat every number as odds, not a promise — the ${a.horizon} thesis is invalidated ${a.invalidation_dir} ${fmtUsd(a.invalidation)}.`;
}

function NewsLinkBar({ nl }) {
  const up = nl.delta > 0;
  const flat = nl.delta === 0;
  return (
    <div className="mt-3 rounded-lg border border-violet-500/25 bg-violet-500/5 p-3">
      <div className="flex items-center gap-2">
        <Newspaper className="h-3.5 w-3.5 text-violet-400" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-violet-300">News Forecast Link</span>
        <span className={`ml-auto text-xs font-bold ${up ? 'text-emerald-400' : flat ? 'text-slate-400' : 'text-red-400'}`}>{up ? '+' : ''}{nl.delta} pts</span>
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs">
        <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-slate-400">base {nl.higher_base}%</span>
        <span className="text-slate-500">→</span>
        <span className={`rounded px-2 py-0.5 font-mono font-bold ${up ? 'bg-emerald-500/10 text-emerald-400' : flat ? 'bg-slate-800 text-slate-300' : 'bg-red-500/10 text-red-400'}`}>adjusted {nl.higher_adj}%</span>
        <span className={`ml-auto rounded border px-1.5 py-0.5 text-[10px] font-semibold ${DIR_COLOR[(nl.bias || 'neutral').toLowerCase()]}`}>{nl.bias} news</span>
      </div>
      {nl.top_driver && <p className="mt-2 text-[11px] text-slate-500">Top driver: <span className="text-slate-400">{nl.top_driver}</span></p>}
    </div>
  );
}

function ForecastCard({ f }) {
  const sym = React.useContext(SymbolContext);
  const nl = f.news_link;
  const eff = nl ? nl.higher_adj : f.higher;
  const effLow = nl ? nl.lower_adj : f.lower;
  const bullish = eff >= 50;
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="mb-2 flex items-center gap-1.5">
        <img src="/albert.png" alt="Albert" className="h-6 w-6 rounded-full object-cover ring-1 ring-sky-500/50" />
        <span className="text-[10px] font-bold uppercase tracking-wider text-sky-300">Albert’s Call</span>
      </div>
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-1 text-lg font-bold text-white">{f.horizon} Forecast<InfoTip text={`The model's probability that ${sym} is higher vs lower at the end of this window, plus bull/base/bear price scenarios. Odds, not a promise.`} /></h3>
        <Badge variant="outline" className={`border-slate-700 ${bullish ? 'text-emerald-400' : 'text-red-400'}`}>{bullish ? 'Leans Up' : 'Leans Down'}</Badge>
      </div>
      {f.calibrated && <p className="mt-1 flex flex-wrap items-center gap-1 text-[10px] font-semibold text-violet-300"><Check className="h-3 w-3" />Isotonic-calibrated odds{f.features_used ? ` · ${f.features_used.length} horizon features` : ''}{f.decaying ? <span className="ml-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-amber-300">down-weighted {Math.round((f.ensemble_weight ?? 1) * 100)}% · model decaying</span> : null}</p>}
      <div className="mt-3">
        <div className="flex justify-between text-sm font-semibold"><span className="text-emerald-400">Higher {eff}%</span><span className="text-red-400">{effLow}% Lower</span></div>
        <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-red-500/40">
          <div className="h-full rounded-full bg-emerald-400" style={{ width: `${eff}%` }} />
        </div>
        {nl && <p className="mt-1 text-[10px] text-slate-500">base model {f.higher}% · adjusted by live news</p>}
      </div>
      {nl && <NewsLinkBar nl={nl} />}
      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-emerald-500/10 p-2"><p className="text-[10px] text-slate-400">Bull</p><p className="text-sm font-bold text-emerald-400">{fmtUsd(f.bull)}</p></div>
        <div className="rounded-lg bg-slate-800/60 p-2"><p className="text-[10px] text-slate-400">Base</p><p className="text-sm font-bold text-slate-200">{fmtUsd(f.base)}</p></div>
        <div className="rounded-lg bg-red-500/10 p-2"><p className="text-[10px] text-slate-400">Bear</p><p className="text-sm font-bold text-red-400">{fmtUsd(f.bear)}</p></div>
      </div>
      {f.quantiles && (
        <div className="mt-4">
          <p className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Price Cone (10–90%)<InfoTip text="A probabilistic price distribution, not a single guess. There's ~80% modelled chance price lands inside the p10–p90 band, with p50 the median. Wider = more uncertain." /></p>
          <div className="relative h-6 w-full rounded-full bg-gradient-to-r from-red-500/25 via-slate-700/40 to-emerald-500/25">
            <div className="absolute inset-y-0 rounded-full bg-sky-500/25" style={{ left: '25%', right: '25%' }} />
            <div className="absolute inset-y-0 w-0.5 bg-white" style={{ left: '50%' }} title="median" />
          </div>
          <div className="mt-1 flex justify-between font-mono text-[10px] text-slate-500">
            <span className="text-red-400">{fmtUsd(f.quantiles.p10)}</span>
            <span>{fmtUsd(f.quantiles.p25)}</span>
            <span className="text-slate-200">{fmtUsd(f.quantiles.p50)}</span>
            <span>{fmtUsd(f.quantiles.p75)}</span>
            <span className="text-emerald-400">{fmtUsd(f.quantiles.p90)}</span>
          </div>
        </div>
      )}
      {f.conformal && (
        <div className="mt-3 rounded-lg border border-sky-500/25 bg-sky-500/[0.06] p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Conformal {f.conformal.target_coverage}% Corridor<InfoTip text="A distribution-free price band with a mathematical coverage guarantee (Conformalized Quantile Regression). Unlike the modelled cone, it's calibrated so the true price lands inside it about this % of the time — verified below." /></span>
            <span className={`ml-auto rounded-full border px-2 py-0.5 text-[10px] font-bold ${Math.abs(f.conformal.coverage - f.conformal.target_coverage) <= 4 ? 'border-emerald-500/40 text-emerald-300' : 'border-amber-500/40 text-amber-300'}`}>
              caught {f.conformal.coverage}% of moves
            </span>
          </div>
          <div className="mt-1.5 flex items-center justify-between font-mono text-sm">
            <span className="font-bold text-red-300">{fmtUsd(f.conformal.lower)}</span>
            <span className="text-[10px] text-slate-500">± band · {f.conformal.width_pct}% wide</span>
            <span className="font-bold text-emerald-300">{fmtUsd(f.conformal.upper)}</span>
          </div>
        </div>
      )}
      {f.ev && (
        <div className={`mt-3 rounded-lg border p-3 ${f.ev.ev_pct > 0 ? 'border-emerald-500/25 bg-emerald-500/[0.06]' : f.ev.ev_pct < 0 ? 'border-red-500/25 bg-red-500/[0.06]' : 'border-slate-800 bg-slate-950/40'}`}>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Expected Value<InfoTip text="EV weighs win probability against payoff size. A sub-50% win-rate can still be profitable if the upside outweighs the downside (payoff > 1). EV = P(up)×avg-up − P(down)×avg-down." /></span>
            <span className={`text-sm font-black ${f.ev.ev_pct > 0 ? 'text-emerald-400' : f.ev.ev_pct < 0 ? 'text-red-400' : 'text-slate-300'}`}>{f.ev.ev_pct > 0 ? '+' : ''}{f.ev.ev_pct}%</span>
          </div>
          <div className="mt-1.5 grid grid-cols-3 gap-2 text-center text-[11px]">
            <div><p className="text-slate-500">Win prob</p><p className="font-mono font-semibold text-slate-200">{f.ev.win_prob}%</p></div>
            <div><p className="text-slate-500">Payoff</p><p className="font-mono font-semibold text-slate-200">{f.ev.payoff_ratio != null ? f.ev.payoff_ratio + ':1' : '—'}</p></div>
            <div><p className="text-slate-500">Verdict</p><p className={`font-semibold ${f.ev.ev_pct > 0 ? 'text-emerald-400' : f.ev.ev_pct < 0 ? 'text-red-400' : 'text-slate-300'}`}>{f.ev.verdict}</p></div>
          </div>
          <p className="mt-1 text-center text-[10px] text-slate-500">+{f.ev.avg_up_pct}% avg upside vs −{f.ev.avg_down_pct}% avg downside</p>
        </div>
      )}
      <div className="mt-4 space-y-1.5 text-xs">
        <div className="flex justify-between"><span className="flex items-center gap-1 text-slate-400">Expected range<InfoTip text="The likely high–low price band for this window based on recent volatility. Price can still move outside it." /></span><span className="font-mono text-slate-200">{fmtUsd(f.expected_low)} – {fmtUsd(f.expected_high)}</span></div>
        <div className="flex justify-between"><span className="flex items-center gap-1 text-slate-400">Confidence<InfoTip text="How strong the model's conviction is on this call, shown as a label and a 0–100%. Higher means the signal setup has been clearer historically." /></span><span className="font-semibold text-sky-400">{f.confidence} ({f.confidence_pct}%)</span></div>
        <div className="flex justify-between"><span className="flex items-center gap-1 text-slate-400">Backtest accuracy<InfoTip text="How often this type of call was correct in historical testing. A track-record hint, not a guarantee of the current call." /></span><span className="text-slate-200">{f.accuracy}%</span></div>
        <div className="flex justify-between"><span className="flex items-center gap-1 text-slate-400">Invalidated {f.invalidation_dir}<InfoTip text="The price level where this thesis is considered wrong. A move past it means the setup has broken and the forecast should be discarded." /></span><span className="font-mono text-amber-400">{fmtUsd(f.invalidation)}</span></div>
        <div className="flex justify-between"><span className="text-slate-400">Expires</span><span className="font-mono text-slate-400">{f.expiry}</span></div>
      </div>
      {f.contributions && f.contributions.length > 0 && (
        <div className="mt-4 border-t border-slate-800 pt-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Factor contributions (SHAP)</p>
          <div className="space-y-1">
            {f.contributions.slice(0, 4).map((ctr) => (
              <div key={ctr.feature} className="flex items-center gap-2 text-xs">
                <span className="w-28 shrink-0 truncate text-slate-400">{ctr.label}</span>
                <div className="flex h-3 flex-1 items-center">
                  <div className="flex w-1/2 justify-end">{ctr.contribution < 0 && <div className="h-2 rounded-l bg-red-400" style={{ width: `${Math.min(100, Math.abs(ctr.contribution) * 12)}%` }} />}</div>
                  <div className="flex w-1/2">{ctr.contribution >= 0 && <div className="h-2 rounded-r bg-emerald-400" style={{ width: `${Math.min(100, ctr.contribution * 12)}%` }} />}</div>
                </div>
                <span className={`w-12 shrink-0 text-right font-mono ${ctr.contribution >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{ctr.contribution >= 0 ? '+' : ''}{ctr.contribution}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

function ProjectionChart({ d }) {
  const sym = React.useContext(SymbolContext);
  const [showCone, setShowCone] = React.useState(true);
  const [showPivots, setShowPivots] = React.useState(true);
  const [showBasis, setShowBasis] = React.useState(true);
  const [showRhyme, setShowRhyme] = React.useState(true);
  const [showAlerts, setShowAlerts] = React.useState(true);
  const [alerts, setAlerts] = React.useState([]);
  const [analog, setAnalog] = React.useState(null);
  const [analogs, setAnalogs] = React.useState([]);
  React.useEffect(() => {
    fetch(`${API_BASE}/v1/time-machine/analogs?k=3`, { cache: 'no-store' })
      .then((r) => r.json()).then((j) => {
        if (j.status === 'ready' && (j.analogs || []).length) { setAnalog(j.analogs[0]); setAnalogs(j.analogs); }
      }).catch(() => {});
  }, []);
  // Your active price alerts for this coin, drawn as dashed lines so you can see
  // how close price is to each one. Refreshes when a new alert is set from chat.
  React.useEffect(() => {
    const pid = getPid();
    const load = () => {
      fetch(`${API_BASE}/v1/price-alerts?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' })
        .then((r) => r.json())
        .then((j) => setAlerts((j.watches || []).filter((w) => (w.asset || 'BTC') === sym)))
        .catch(() => {});
    };
    load();
    const id = setInterval(load, 20000);
    const onCreated = () => load();
    window.addEventListener('btciq:alert-created', onCreated);
    return () => { clearInterval(id); window.removeEventListener('btciq:alert-created', onCreated); };
  }, [sym]);

  const last = d.last_close;
  const hist = (d.performance || []).slice(-60).map((p, i, arr) => ({ x: i - (arr.length - 1), price: p.btcPrice, label: p.date }));
  const fcs = (d.forecasts || []).slice().sort((a, b) => (a.days || 0) - (b.days || 0));

  // Merge everything onto a single numeric x-axis (day offset; 0 = now).
  const rows = new Map();
  const put = (x, patch) => { rows.set(x, { ...(rows.get(x) || { x }), ...patch }); };
  hist.forEach((h) => put(h.x, { price: h.price }));
  put(0, { price: last, base: last, cone: showCone ? [last, last] : undefined, rhyme: last });
  fcs.forEach((f) => {
    const lo = f.conformal?.lower ?? f.bear;
    const hi = f.conformal?.upper ?? f.bull;
    put(f.days || 1, { base: f.base, cone: showCone ? [lo, hi] : undefined });
  });
  if (analog && showRhyme && analog.path_30d?.length) {
    const p0 = analog.path_30d[0].close;
    analog.path_30d.forEach((p) => { if (p0) put(p.d, { rhyme: Math.round(last * (p.close / p0)) }); });
  }
  if (showRhyme && analogs.length > 1) {
    // Confidence band = min/max across ALL top-K analog forward paths (anchored to today).
    const maxD = Math.max(...analogs.map((a) => (a.path_30d || []).length - 1));
    for (let dd = 0; dd <= maxD; dd++) {
      const prices = analogs.map((a) => {
        const p0 = a.path_30d?.[0]?.close; const pv = a.path_30d?.[dd]?.close;
        return (p0 && pv != null) ? last * (pv / p0) : null;
      }).filter((x) => x != null);
      if (prices.length > 1) put(dd, { aband: [Math.round(Math.min(...prices)), Math.round(Math.max(...prices))] });
    }
    put(0, { aband: [last, last] });
  }
  const data = [...rows.values()].sort((a, b) => a.x - b.x);
  const cb = d.cost_basis || {};
  const fmtK = (v) => (v == null ? '' : `$${(v / 1000).toFixed(1)}k`);

  const Chip = ({ on, set, color, children }) => (
    <button onClick={() => set(!on)} className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors ${on ? `${color} text-white` : 'border-slate-700 bg-slate-800/50 text-slate-400'}`}>{children}</button>
  );

  return (
    <Card className="border-0 bg-slate-900 p-4 ring-1 ring-slate-800">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-slate-100">
          <Target className="h-4 w-4 text-sky-400" />Projection & Overlays
          <InfoTip below text="Recent price with the forward 90% conformal price corridor (shaded), Albert's take-profit (bull) & invalidation pivots, volume-weighted short/long-term holder cost-basis proxies, and the closest FAISS historical analog's forward path anchored to today ('rhyme' line). Toggle each overlay." />
        </h3>
        <div className="ml-auto flex flex-wrap gap-1.5">
          <Chip on={showCone} set={setShowCone} color="border-sky-500/50 bg-sky-500/70">Conformal cone</Chip>
          <Chip on={showPivots} set={setShowPivots} color="border-emerald-500/50 bg-emerald-500/70">TP / invalidation</Chip>
          <Chip on={showBasis} set={setShowBasis} color="border-amber-500/50 bg-amber-500/70">Cost basis</Chip>
          {analog && <Chip on={showRhyme} set={setShowRhyme} color="border-violet-500/50 bg-violet-500/70">Analog rhyme</Chip>}
          {alerts.length > 0 && <Chip on={showAlerts} set={setShowAlerts} color="border-amber-400/50 bg-amber-400/70">My alerts</Chip>}
        </div>
      </div>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="x" type="number" domain={['dataMin', 'dataMax']} tick={{ fill: '#64748b', fontSize: 10 }}
              tickFormatter={(v) => (v === 0 ? 'now' : v > 0 ? `+${v}d` : `${v}d`)} />
            <YAxis domain={['auto', 'auto']} tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={fmtK} width={48} />
            <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }}
              labelFormatter={(v) => (v === 0 ? 'Now' : v > 0 ? `+${v} days (forecast)` : `${-v} days ago`)}
              formatter={(val, name) => {
                if (name === 'cone' && Array.isArray(val)) return [`${fmtUsd(val[0])} – ${fmtUsd(val[1])}`, '90% corridor'];
                if (name === 'aband' && Array.isArray(val)) return [`${fmtUsd(val[0])} – ${fmtUsd(val[1])}`, 'analog spread'];
                if (val == null) return [null, null];
                const lbl = name === 'price' ? 'Price' : name === 'base' ? 'Projected base' : name === 'rhyme' ? 'Analog rhyme' : name;
                return [fmtUsd(val), lbl];
              }} />
            {showCone && <Area dataKey="cone" stroke="#38bdf8" strokeOpacity={0.4} fill="#38bdf8" fillOpacity={0.14} connectNulls isAnimationActive={false} />}
            {showRhyme && analogs.length > 1 && <Area dataKey="aband" stroke="#a78bfa" strokeOpacity={0.25} fill="#a78bfa" fillOpacity={0.1} connectNulls isAnimationActive={false} />}
            {analog && showRhyme && <Line dataKey="rhyme" stroke="#a78bfa" strokeWidth={1.5} strokeDasharray="4 3" dot={false} connectNulls isAnimationActive={false} />}
            <Line dataKey="price" stroke="#e2e8f0" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            {showCone && <Line dataKey="base" stroke="#38bdf8" strokeWidth={1.5} strokeDasharray="5 4" dot={{ r: 2 }} connectNulls isAnimationActive={false} />}
            <ReferenceLine x={0} stroke="#475569" strokeDasharray="2 2" />
            {showBasis && cb.sth != null && (
              <ReferenceLine y={cb.sth} stroke="#f59e0b" strokeDasharray="6 3"
                label={{ value: `STH basis ${fmtK(cb.sth)}`, position: 'insideLeft', fill: '#f59e0b', fontSize: 10 }} />
            )}
            {showBasis && cb.lth != null && (
              <ReferenceLine y={cb.lth} stroke="#a78bfa" strokeDasharray="6 3"
                label={{ value: `LTH basis ${fmtK(cb.lth)}`, position: 'insideLeft', fill: '#a78bfa', fontSize: 10 }} />
            )}
            {showPivots && fcs.map((f) => (
              <ReferenceLine key={`inv-${f.horizon}`} y={f.invalidation} stroke="#f87171" strokeOpacity={0.55} strokeDasharray="3 3"
                label={{ value: `${f.horizon} invalidation`, position: 'right', fill: '#f87171', fontSize: 9 }} />
            ))}
            {showPivots && fcs.map((f) => (
              <ReferenceLine key={`tp-${f.horizon}`} y={f.bull} stroke="#34d399" strokeOpacity={0.45} strokeDasharray="3 3"
                label={{ value: `${f.horizon} TP`, position: 'right', fill: '#34d399', fontSize: 9 }} />
            ))}
            {showAlerts && alerts.map((w) => (
              <ReferenceLine key={`al-${w.id}`} y={w.level} stroke="#fbbf24" strokeWidth={1.5} strokeDasharray="2 2"
                label={{ value: `Alert ${fmtK(w.level)}`, position: 'insideLeft', fill: '#fbbf24', fontSize: 9 }} />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-slate-500">
        <span className="flex items-center gap-1"><span className="h-2 w-4 rounded-sm bg-sky-400/40" />90% conformal corridor</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-4" style={{ borderTop: '2px dashed #34d399' }} />take-profit (bull)</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-4" style={{ borderTop: '2px dashed #f87171' }} />invalidation</span>
        {analog && showRhyme && <span className="flex items-center gap-1"><span className="h-0.5 w-4" style={{ borderTop: '2px dashed #a78bfa' }} />analog rhyme ({analog.date})</span>}
        {showRhyme && analogs.length > 1 && <span className="flex items-center gap-1"><span className="h-2 w-4 rounded-sm bg-violet-400/25" />analog spread (top {analogs.length})</span>}
        {showBasis && (cb.sth != null || cb.lth != null) && (
          <span className="ml-auto italic">Cost basis = volume-weighted price proxy ({cb.sth_window}d / {cb.lth_window}d), not on-chain realized price.</span>
        )}
      </div>
    </Card>
  );
}


function ForecastsSection({ d }) {
  return (
    <div className="space-y-5">
      <SectionHead icon={Target} title="Forecasts" blurb={SECTIONS[1].blurb} coin={d.symbol || 'BTC'} />
      <AiReview text={reviewForecasts(d)} section="forecasts" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {(d.forecasts || []).map((f) => <ForecastCard key={f.horizon} f={f} />)}
      </div>
      <ProjectionChart d={d} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <div className="mb-3 flex items-center gap-2">
            <img src="/albert.png" alt="Albert" className="h-10 w-10 shrink-0 rounded-full object-cover ring-2 ring-emerald-500/40" />
            <div>
              <h3 className="flex items-center gap-1.5 font-semibold text-slate-100"><TrendingUp className="h-4 w-4 text-emerald-400" />Albert’s Call · Why it could go up</h3>
              <p className="text-[11px] text-slate-500">Albert’s read of the bullish evidence</p>
            </div>
          </div>
          <ul className="space-y-2">{d.factors.bullish.map((t, i) => <li key={i} className="flex gap-2 text-sm text-slate-300"><Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />{t}</li>)}</ul>
        </Card>
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <div className="mb-3 flex items-center gap-2">
            <img src="/albert.png" alt="Albert" className="h-10 w-10 shrink-0 rounded-full object-cover ring-2 ring-red-500/40" />
            <div>
              <h3 className="flex items-center gap-1.5 font-semibold text-slate-100"><TrendingDown className="h-4 w-4 text-red-400" />Albert’s Call · Why it could go down</h3>
              <p className="text-[11px] text-slate-500">Albert’s read of the downside risks</p>
            </div>
          </div>
          <ul className="space-y-2">{d.factors.risk.map((t, i) => <li key={i} className="flex gap-2 text-sm text-slate-300"><X className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />{t}</li>)}</ul>
        </Card>
      </div>
    </div>
  );
}


const bmConfColor = (c) => ({ High: 'text-emerald-400', Moderate: 'text-lime-400',
  Low: 'text-amber-400', 'Very Low': 'text-orange-400' }[c] || 'text-slate-400');
const bmVol = (v) => ({ 'Very High': ['bg-red-500', 100], High: ['bg-orange-500', 78],
  Elevated: ['bg-amber-500', 52], Low: ['bg-emerald-500', 26] }[v] || ['bg-slate-600', 40]);
const scenColor = (n) => ({ 'Adoption Expansion': 'text-emerald-400', 'Base Adoption': 'text-sky-400',
  'Restrictive Policy': 'text-amber-400', 'Severe Disruption': 'text-red-400' }[n] || 'text-slate-300');

function BmHorizonCard({ h }) {
  const up = h.prob_above >= 50;
  const [vc, vp] = bmVol(h.expected_volatility);
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="mb-2 flex items-center gap-1.5">
        <img src="/albert.png" alt="Albert" className="h-6 w-6 rounded-full object-cover ring-1 ring-sky-500/50" />
        <span className="text-[10px] font-bold uppercase tracking-wider text-sky-300">Albert’s Call</span>
      </div>
      <div className="flex items-center justify-between">
        <div><h3 className="text-base font-bold text-white">{h.label}</h3><p className="text-[11px] text-slate-500">{h.horizon} horizon</p></div>
        <Badge variant="outline" className={`border-slate-700 ${up ? 'text-emerald-400' : 'text-red-400'}`}>{up ? 'Leans Up' : 'Leans Down'}</Badge>
      </div>
      <div className="mt-3 flex justify-between text-sm font-semibold"><span className="text-emerald-400">Above {h.prob_above}%</span><span className="text-red-400">{h.prob_below}% Below</span></div>
      <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-red-500/40"><div className="h-full rounded-full bg-emerald-400" style={{ width: `${h.prob_above}%` }} /></div>
      <div className="mt-3 space-y-1.5 text-sm">
        <div className="flex justify-between"><span className="text-slate-500">Base case</span><span className="font-mono font-semibold text-slate-200">{fmtUsd(h.base_low)}–{fmtUsd(h.base_high)}</span></div>
        <div className="flex justify-between"><span className="text-emerald-400/70">Bull case</span><span className="font-mono text-emerald-400">{fmtUsd(h.bull_low)}–{fmtUsd(h.bull_high)}</span></div>
        <div className="flex justify-between"><span className="text-red-400/70">Bear case</span><span className="font-mono text-red-400">{fmtUsd(h.bear_low)}–{fmtUsd(h.bear_high)}</span></div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div><p className="text-slate-500">Expected volatility</p><div className="mt-1 flex items-center gap-1.5"><div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800"><div className={`h-full rounded-full ${vc}`} style={{ width: `${vp}%` }} /></div></div><p className="mt-0.5 text-slate-400">{h.expected_volatility}</p></div>
        <div><p className="text-slate-500">Model confidence</p><p className={`mt-1 font-bold ${bmConfColor(h.model_confidence)}`}>{h.model_confidence}</p>{h.accuracy != null && <p className="text-[10px] text-slate-500">backtest {h.accuracy}%</p>}</div>
      </div>
      <div className="mt-3 border-t border-slate-800 pt-2 text-xs">
        <p className="text-emerald-400/90">▲ {h.top_positive}</p>
        <p className="mt-1 text-red-400/90">▼ {h.top_risk}</p>
      </div>
      <div className="mt-3">
        <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">What drives this horizon</p>
        <div className="space-y-1">
          {h.weighting.slice(0, 4).map((w) => (
            <div key={w.category} className="flex items-center gap-2 text-[11px]">
              <span className="w-32 shrink-0 truncate text-slate-400">{w.category}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-gradient-to-r from-sky-500 to-violet-500" style={{ width: `${w.weight * 2}%` }} /></div>
              <span className="w-7 text-right font-mono text-slate-400">{w.weight}%</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function BmScenarioCard({ h }) {
  return (
    <Card className="border-0 bg-gradient-to-br from-violet-500/[0.06] to-slate-900 p-5 ring-1 ring-violet-500/20">
      <div className="mb-2 flex items-center gap-1.5">
        <img src="/albert.png" alt="Albert" className="h-6 w-6 rounded-full object-cover ring-1 ring-violet-500/50" />
        <span className="text-[10px] font-bold uppercase tracking-wider text-violet-300">Albert’s Call</span>
      </div>
      <div className="flex items-center justify-between">
        <div><h3 className="text-base font-bold text-white">{h.label}</h3><p className="text-[11px] text-slate-500">{h.horizon} · broad scenarios, not a single target</p></div>
        <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${bmConfColor(h.model_confidence)} border-slate-700`}>Confidence {h.model_confidence}</span>
      </div>
      <div className="mt-3 space-y-2.5">
        {h.scenarios.map((s) => (
          <div key={s.name}>
            <div className="flex items-center justify-between text-xs">
              <span className={`font-semibold ${scenColor(s.name)}`}>{s.name}</span>
              <span className="font-mono text-slate-300">{fmtUsd(s.low)}–{fmtUsd(s.high)} <span className="text-slate-500">· {s.prob}%</span></span>
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-800"><div className={`h-full rounded-full ${scenColor(s.name).replace('text-', 'bg-')}`} style={{ width: `${s.prob * 2.2}%` }} /></div>
            <p className="mt-0.5 text-[10px] text-slate-500">{s.note}</p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-slate-500">The further out the forecast, the wider the range and the lower the certainty.</p>
    </Card>
  );
}

function WhyChangedPanel({ bm }) {
  const [open, setOpen] = React.useState(null);
  const byName = {};
  (bm.horizons || []).forEach((h) => { byName[h.label] = h; byName[h.horizon] = h; });
  const changes = bm.changes || [];
  return (
    <Card className="border-0 bg-gradient-to-br from-sky-500/[0.06] to-slate-900 p-5 ring-1 ring-sky-500/20">
      <div className="mb-2 flex items-center gap-2.5">
        <img src="/albert.png" alt="Albert" className="h-10 w-10 rounded-full object-cover ring-2 ring-sky-500/40" />
        <h3 className="text-sm font-semibold text-white">Why the forecast changed</h3>
      </div>
      <p className="text-sm leading-relaxed text-slate-300">{bm.change_explanation}</p>
      {changes.length > 0 ? (
        <div className="mt-3 space-y-1.5">
          {changes.map((c, i) => {
            const h = byName[c.horizon];
            const isOpen = open === i;
            return (
              <div key={i} className="rounded-lg border border-slate-800 bg-slate-950/40">
                <button onClick={() => setOpen(isOpen ? null : i)} className="flex w-full items-center gap-3 p-2.5 text-left text-sm">
                  <span className="w-10 font-bold text-slate-200">{c.horizon}</span>
                  <span className="text-slate-400">prob. higher {c.from}% → {c.to}%</span>
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${c.prob_delta > 0 ? 'border-emerald-500/30 text-emerald-300' : c.prob_delta < 0 ? 'border-red-500/30 text-red-300' : 'border-slate-700 text-slate-400'}`}>{c.prob_delta > 0 ? '+' : ''}{c.prob_delta}pt</span>
                  <span className="ml-auto text-slate-500">{isOpen ? '▲' : '▼'}</span>
                </button>
                {isOpen && h && (
                  <div className="space-y-2 border-t border-slate-800 p-3 text-sm">
                    <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2.5"><p className="text-[10px] font-semibold uppercase text-emerald-400">Supporting factor</p><p className="mt-0.5 text-slate-300">{h.top_positive}</p></div>
                    <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-2.5"><p className="text-[10px] font-semibold uppercase text-red-400">Offsetting risk</p><p className="mt-0.5 text-slate-300">{h.top_risk}</p></div>
                    <p className="text-[11px] text-slate-500">Affects the <span className="font-semibold text-slate-300">{c.horizon}</span> horizon · confidence {h.model_confidence} · expected volatility {h.expected_volatility}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="mt-2 text-xs text-slate-500">No material change since the previous run — the drivers are steady.</p>
      )}
      <p className="mt-3 text-[11px] text-slate-600">Tap a horizon to see the strongest factor for and against it. Factors are the model’s current interpretation of live signals — not guaranteed causes.</p>
    </Card>
  );
}

function BitMarkSection({ d }) {
  const bm = d.bitmark;
  const [running, setRunning] = React.useState(false);
  const [runMsg, setRunMsg] = React.useState(null);
  if (!bm) return <ComingSoonSection section={sec('bitmark')} />;
  const trigLabel = { scheduled: 'Scheduled', manual: 'Manual run', event: 'Event-triggered' }[bm.trigger] || bm.trigger;
  const trigColor = bm.trigger === 'event' ? 'text-orange-300 border-orange-500/30' : bm.trigger === 'manual' ? 'text-sky-300 border-sky-500/30' : 'text-slate-300 border-slate-700';
  const models = bm.horizons.filter((h) => h.type === 'model');
  const scenarios = bm.horizons.filter((h) => h.type === 'scenario');
  const runForecast = async () => {
    if (running) return;
    setRunning(true); setRunMsg(null);
    const passcode = (typeof window !== 'undefined' && window.localStorage.getItem('btciq_admin_passcode')) || '';
    try {
      const r = await fetch(`${API_BASE}/v1/bitmark/run`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passcode }),
      });
      const j = await r.json();
      setRunMsg({ status: j.status, text: j.status === 'unauthorized' ? 'Admin passcode required — set it in Settings to run a manual forecast.' : j.message });
    } catch (e) { setRunMsg({ status: 'error', text: 'Could not start a forecast — please try again.' }); }
    finally { setRunning(false); }
  };
  return (
    <div className="space-y-5">
      <SectionHead icon={Sparkles} title="CryptoMarkAI" blurb={sec('bitmark').blurb} coin={d.symbol || 'BTC'} />

      <Card className="border-0 bg-gradient-to-br from-amber-500/[0.08] via-violet-500/[0.08] to-slate-900 p-6 ring-1 ring-amber-500/25">
        <div className="flex flex-wrap items-center gap-4">
          <div className="rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 p-2.5"><Sparkles className="h-6 w-6 text-white" /></div>
          <div>
            <h2 className="text-xl font-black text-white">CryptoMarkAI <span className="text-sm font-medium text-slate-400">Bitcoin Price Prediction Engine</span></h2>
            <p className="text-xs text-slate-400">Adaptive, probability-based forecasts · 1 week to 5 years · model {bm.model_version}</p>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-3">
            <div className="text-right text-xs">
              <span className={`rounded-full border px-2 py-0.5 font-semibold ${trigColor}`}>{trigLabel}</span>
              <p className="mt-1 text-slate-500">Issued {bm.issued} · next {bm.next_scheduled_update}</p>
            </div>
            <Button onClick={runForecast} disabled={running} className="gap-2 bg-gradient-to-r from-amber-500 to-orange-500 text-white shadow-lg shadow-amber-500/20 hover:from-amber-400 hover:to-orange-400">
              <RefreshCw className={`h-4 w-4 ${running ? 'animate-spin' : ''}`} />Run New Forecast
            </Button>
          </div>
        </div>
        {runMsg && (
          <div className={`mt-3 rounded-lg border p-3 text-sm ${runMsg.status === 'rate_limited' ? 'border-amber-500/30 bg-amber-500/10 text-amber-200' : runMsg.status === 'started' ? 'border-sky-500/30 bg-sky-500/10 text-sky-200' : 'border-slate-700 bg-slate-800/40 text-slate-300'}`}>{runMsg.text}</div>
        )}
      </Card>

      <WhyChangedPanel bm={bm} />

      <div>
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Model forecasts · 1 week to 1 year</p>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {models.map((h) => <BmHorizonCard key={h.horizon} h={h} />)}
        </div>
      </div>
      <div>
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Long-range scenarios · 2 & 5 years</p>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {scenarios.map((h) => <BmScenarioCard key={h.horizon} h={h} />)}
        </div>
      </div>
      <p className="text-center text-[11px] text-slate-600">CryptoMarkAI · powered by CryptoCentAI · probability-based research, not financial advice.</p>
    </div>
  );
}

/* ----------------- Prediction Ledger / Scorecard --------------------- */

function ForecastsHubSection({ d }) {
  const isBtc = React.useContext(SymbolContext) === 'BTC';
  return (
    <div className="space-y-8">
      {isBtc && <BitMarkSection d={d} />}
      <ForecastsSection d={d} />
    </div>
  );
}

export default ForecastsHubSection;
