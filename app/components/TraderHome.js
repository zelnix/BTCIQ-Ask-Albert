'use client';
// Trader Home cockpit — the plain-first landing view. Consumes the deterministic
// GET /api/v1/albert/trader-home aggregation and renders a 3-second hierarchy:
// (1) the signal + conviction, (2) an executive briefing with deep-links,
// (3) a projection cone (forecast bands, anchored + safety-gated), (4) the evidence
// (drivers / historical edge), the user's portfolio impact, an honest integrity
// strip, and a drill-down Performance module (fees vs buy & hold). Advisory / paper only.
import React from 'react';
import { API_BASE, getPid } from '../lib/api';
import {
  Loader2, TrendingUp, TrendingDown, Minus, ShieldCheck, Activity, Gauge,
  CheckCircle2, AlertTriangle, Layers, Clock, ArrowRight, LineChart, ChevronDown,
  BarChart3, Wallet, Info, Flag,
} from 'lucide-react';

/* ---------------------------------- format ------------------------------- */
const fmtUsd = (n, d = 0) => (n == null || Number.isNaN(Number(n))
  ? '\u2014'
  : '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: d }));
const fmtPct = (n, d = 1) => (n == null || Number.isNaN(Number(n))
  ? '\u2014'
  : `${n >= 0 ? '+' : ''}${Number(n).toFixed(d)}%`);
const pctColor = (n) => (n == null ? 'text-slate-300' : n >= 0 ? 'text-emerald-400' : 'text-rose-400');

const callTone = (call) => {
  const c = (call || '').toLowerCase();
  if (c.includes('bull') || c.includes('buy') || c.includes('long')) return { fg: 'text-emerald-300', bg: 'bg-emerald-500/10', ring: 'ring-emerald-500/30', Icon: TrendingUp };
  if (c.includes('bear') || c.includes('sell') || c.includes('short')) return { fg: 'text-rose-300', bg: 'bg-rose-500/10', ring: 'ring-rose-500/30', Icon: TrendingDown };
  return { fg: 'text-slate-200', bg: 'bg-slate-500/10', ring: 'ring-slate-500/30', Icon: Minus };
};

// Route an executive-briefing phrase to the most relevant dashboard section.
const briefingRoute = (txt) => {
  const t = (txt || '').toLowerCase();
  if (/(news|headline|flow)/.test(t)) return { section: 'news', label: 'News' };
  if (/(macro|policy|liquidity|dxy|fed|rate)/.test(t)) return { section: 'macro', label: 'Macro' };
  if (/(technical|chart|structure|trend|regime|momentum)/.test(t)) return { section: 'overview', label: 'Technicals' };
  if (/(risk|drawdown|protection|volatil)/.test(t)) return { section: 'risk', label: 'Risk' };
  if (/(halving|cycle|dominance)/.test(t)) return { section: 'market-intel', label: 'Market' };
  return null;
};

/* -------------------------------- projection ----------------------------- */
// A proper fan/cone chart across horizons: anchored at t0 = anchorPrice, then
// bull / base / bear lines out to each horizon, with the shaded uncertainty band.
function ProjectionCone({ projection, symbol, selected, onSelect }) {
  const hs = (projection?.horizons || []).filter((h) => h.base != null);
  if (!hs.length) return null;
  const anchor = projection.anchorPrice || projection.priceNow;
  const W = 520, H = 190, padL = 8, padR = 8, padT = 14, padB = 22;
  const n = hs.length;
  const xs = (i) => padL + ((W - padL - padR) * (i + 1)) / n; // i=-1 => anchor at x0
  const x0 = padL;
  const allVals = [anchor, ...hs.flatMap((h) => [h.bull, h.bear, h.base])].filter((v) => v != null);
  const lo = Math.min(...allVals), hi = Math.max(...allVals);
  const pad = (hi - lo) * 0.08 || 1;
  const yMin = lo - pad, yMax = hi + pad;
  const ys = (v) => padT + (H - padT - padB) * (1 - (v - yMin) / (yMax - yMin || 1));
  const line = (key) => `${x0},${ys(anchor)} ` + hs.map((h, i) => `${xs(i)},${ys(h[key])}`).join(' ');
  const area = `${x0},${ys(anchor)} ` + hs.map((h, i) => `${xs(i)},${ys(h.bull)}`).join(' ')
    + ' ' + hs.slice().reverse().map((h, i) => `${xs(n - 1 - i)},${ys(h.bear)}`).join(' ');

  return (
    <div className="mt-3">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 200 }}>
        <polygon points={area} fill="rgba(56,189,248,0.10)" stroke="none" />
        <polyline points={line('bull')} fill="none" stroke="rgba(52,211,153,0.55)" strokeWidth="1.5" strokeDasharray="4 3" />
        <polyline points={line('bear')} fill="none" stroke="rgba(248,113,113,0.55)" strokeWidth="1.5" strokeDasharray="4 3" />
        <polyline points={line('base')} fill="none" stroke="#38bdf8" strokeWidth="2" />
        {/* anchor marker */}
        <circle cx={x0} cy={ys(anchor)} r="3" fill="#e2e8f0" />
        {hs.map((h, i) => {
          const on = h.horizon === selected;
          return (
            <g key={h.horizon} onClick={() => onSelect(h.horizon)} style={{ cursor: 'pointer' }}>
              <line x1={xs(i)} y1={padT} x2={xs(i)} y2={H - padB} stroke={on ? 'rgba(56,189,248,0.35)' : 'transparent'} strokeWidth="1" />
              <circle cx={xs(i)} cy={ys(h.base)} r={on ? 4 : 2.5} fill={on ? '#38bdf8' : '#64748b'} />
              <text x={xs(i)} y={H - 7} textAnchor="middle" fontSize="9" fill={on ? '#7dd3fc' : '#64748b'}>{h.horizon}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function EventStrip({ projection, horizonDays }) {
  const pins = (projection?.eventPins || []).filter((p) => p.daysUntil != null && (horizonDays == null || p.daysUntil <= horizonDays));
  if (projection && projection.eventsAvailable === false) {
    return <p className="mt-2 text-[10px] text-slate-500">Event calendar unavailable.</p>;
  }
  if (!pins.length) return null;
  const span = Math.max(1, horizonDays || Math.max(...pins.map((p) => p.daysUntil)));
  const typeTone = (t) => (t === 'Macro' ? 'bg-sky-400' : t === 'Derivatives' ? 'bg-violet-400' : 'bg-slate-400');
  return (
    <div className="mt-3">
      <p className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500"><Flag className="h-3 w-3" />Timing risk (scheduled events — not direction)</p>
      <div className="relative mb-2 h-6">
        <div className="absolute left-0 right-0 top-3 h-px bg-slate-800" />
        {pins.map((p, i) => {
          const left = Math.max(0, Math.min(100, (p.daysUntil / span) * 100));
          return (
            <div key={i} className="absolute -translate-x-1/2" style={{ left: `${left}%`, top: 0 }} title={`${p.title} · ${p.date} · ${p.importance || ''} ${p.expectedVolatility ? '· vol ' + p.expectedVolatility : ''} · ${p.source}`}>
              <span className={`block h-3 w-3 rotate-45 rounded-sm ${typeTone(p.type)}`} />
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {pins.slice(0, 6).map((p, i) => (
          <span key={i} className="inline-flex items-center gap-1 rounded-md border border-slate-800 bg-slate-950/60 px-1.5 py-0.5 text-[9.5px] text-slate-400">
            <span className={`h-1.5 w-1.5 rotate-45 ${typeTone(p.type)}`} />
            {p.title.replace(/\s*\(approx\.\)/i, '')} · {p.daysUntil}d
          </span>
        ))}
      </div>
    </div>
  );
}


function ProjectionPanel({ projection, symbol, selected, onSelect, highlight }) {
  if (!projection || !projection.available) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
        <p className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><LineChart className="h-3.5 w-3.5 text-sky-300" />Projection</p>
        <p className="text-[12px] text-slate-500">{projection?.note || 'Forecast bands are not available yet.'}</p>
      </div>
    );
  }
  const hs = projection.horizons || [];
  const cur = hs.find((h) => h.horizon === selected) || hs[0];
  const paused = !!projection.stale; // feed delay -> pause the forward path (spec 7.1)
  return (
    <div id="th-projection" className={`rounded-2xl border bg-slate-950/40 p-4 transition-shadow ${highlight ? 'border-sky-500/60 ring-2 ring-sky-500/30' : 'border-slate-800'}`}>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><LineChart className="h-3.5 w-3.5 text-sky-300" />Projection · {symbol}</p>
        {!paused && (
          <div className="flex flex-wrap gap-1">
            {hs.map((h) => (
              <button key={h.horizon} onClick={() => onSelect(h.horizon)}
                className={`rounded-md px-2 py-0.5 text-[10px] font-semibold ${h.horizon === (cur?.horizon) ? 'bg-sky-500/20 text-sky-200' : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'}`}>{h.horizon}</button>
            ))}
          </div>
        )}
      </div>

      {paused ? (
        <div className="mt-2 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-[12px] text-amber-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-semibold">Projection paused because current inputs are delayed.</p>
            <p className="mt-0.5 text-[11px] text-amber-300/80">Last engine run {fmtUsd(projection.anchorPrice)} · live {fmtUsd(projection.priceNow)}{projection.liveDriftPct != null ? ` (${fmtPct(projection.liveDriftPct)})` : ''}. The forward path returns once feeds refresh.</p>
          </div>
        </div>
      ) : (
        <>
          <ProjectionCone projection={projection} symbol={symbol} selected={cur?.horizon} onSelect={onSelect} />
          {projection.driftWarning && (
            <div className="mt-2 flex items-start gap-1.5 rounded-lg border border-amber-500/25 bg-amber-500/5 px-2.5 py-1.5 text-[10.5px] text-amber-300/90">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>Bands anchored to {fmtUsd(projection.anchorPrice)}; live is {fmtPct(projection.liveDriftPct)} away — treat with extra caution.</span>
            </div>
          )}
          {cur && (
            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-[11px]">
              <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-2">
                <p className="text-[9px] uppercase tracking-wide text-rose-300/70">Bear</p>
                <p className="font-mono font-semibold text-rose-300">{fmtUsd(cur.bear)}</p>
                <p className={`text-[10px] ${pctColor(cur.bearPct)}`}>{fmtPct(cur.bearPct)}</p>
              </div>
              <div className="rounded-lg border border-sky-500/25 bg-sky-500/10 p-2">
                <p className="text-[9px] uppercase tracking-wide text-sky-300/80">Expected</p>
                <p className="font-mono font-semibold text-sky-200">{fmtUsd(cur.base)}</p>
                <p className={`text-[10px] ${pctColor(cur.basePct)}`}>{fmtPct(cur.basePct)}</p>
              </div>
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2">
                <p className="text-[9px] uppercase tracking-wide text-emerald-300/70">Bull</p>
                <p className="font-mono font-semibold text-emerald-300">{fmtUsd(cur.bull)}</p>
                <p className={`text-[10px] ${pctColor(cur.bullPct)}`}>{fmtPct(cur.bullPct)}</p>
              </div>
            </div>
          )}
          {cur && (
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10.5px] text-slate-400">
              <span className="flex items-center gap-1">Odds <b className={cur.lean === 'UP' ? 'text-emerald-300' : 'text-rose-300'}>{cur.probUp != null ? `${cur.probUp}% up` : '\u2014'}</b></span>
              {cur.confidence && <span>Confidence <b className="text-slate-200">{cur.confidence}</b></span>}
              {cur.evVerdict && <span>EV <b className={/positive/i.test(cur.evVerdict) ? 'text-emerald-300' : /negative/i.test(cur.evVerdict) ? 'text-rose-300' : 'text-slate-200'}>{cur.evPct != null ? `${cur.evPct}%` : ''} {cur.evVerdict}</b></span>}
              {cur.invalidation != null && <span>Invalidated {cur.invalidationDir} <b className="text-amber-300">{fmtUsd(cur.invalidation)}</b></span>}
              {cur.expiry && <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{cur.expiry}</span>}
            </div>
          )}
          {projection.bandCoverage && (
            <p className="mt-1.5 text-[9.5px] text-slate-500">Bands: outer {projection.bandCoverage.outer}, inner {projection.bandCoverage.inner}. {projection.method}</p>
          )}
          <EventStrip projection={projection} horizonDays={cur?.days} />
        </>
      )}
      <p className="mt-2 text-[9.5px] leading-relaxed text-slate-600">{projection.disclaimer}</p>
    </div>
  );
}

/* -------------------------------- performance ---------------------------- */
function DualSpark({ a, b }) {
  // a = benchmark series, b = model series; both [{date,value}] rebased to 100.
  const va = (a || []).map((p) => p.value), vb = (b || []).map((p) => p.value);
  const all = [...va, ...vb, 100];
  if (all.length < 3) return null;
  const lo = Math.min(...all), hi = Math.max(...all);
  const W = 520, H = 120, pad = 6;
  const path = (vals) => vals.map((v, i) => {
    const x = pad + (W - 2 * pad) * (i / Math.max(1, vals.length - 1));
    const y = pad + (H - 2 * pad) * (1 - (v - lo) / (hi - lo || 1));
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const y100 = pad + (H - 2 * pad) * (1 - (100 - lo) / (hi - lo || 1));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full" style={{ maxHeight: 130 }}>
      <line x1={pad} y1={y100} x2={W - pad} y2={y100} stroke="rgba(148,163,184,0.25)" strokeWidth="1" strokeDasharray="3 3" />
      <path d={path(va)} fill="none" stroke="#94a3b8" strokeWidth="1.75" />
      <path d={path(vb)} fill="none" stroke="#38bdf8" strokeWidth="2" />
    </svg>
  );
}

function Kpi({ label, value, sub, tone }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
      <p className="text-[9.5px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`font-mono text-[13px] font-semibold ${tone || 'text-slate-200'}`}>{value}</p>
      {sub && <p className="text-[9.5px] text-slate-500">{sub}</p>}
    </div>
  );
}

function PerformancePanel({ symbol, open, onToggle, highlight }) {
  const [d, setD] = React.useState(null);
  const [err, setErr] = React.useState(false);
  const [view, setView] = React.useState('model'); // 'model' | 'portfolio'
  React.useEffect(() => {
    if (!open || d || err) return;
    let alive = true;
    const pid = getPid();
    fetch(`${API_BASE}/v1/albert/performance?symbol=${encodeURIComponent(symbol)}&pid=${encodeURIComponent(pid || '')}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => { if (alive) (j && j.status !== 'error' ? setD(j) : setErr(true)); })
      .catch(() => { if (alive) setErr(true); });
    return () => { alive = false; };
  }, [open, symbol]); // eslint-disable-line
  React.useEffect(() => { setD(null); setErr(false); }, [symbol]);

  const m = d?.model || {};
  const pv = d?.portfolioView;
  const hasPortfolio = pv && pv.equity != null;

  return (
    <div id="th-performance" className={`rounded-2xl border bg-slate-950/40 p-4 transition-shadow ${highlight ? 'border-violet-500/60 ring-2 ring-violet-500/30' : 'border-slate-800'}`}>
      <button onClick={onToggle} className="flex w-full items-center justify-between">
        <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><BarChart3 className="h-3.5 w-3.5 text-violet-300" />Performance drill-down</span>
        <ChevronDown className={`h-4 w-4 text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="mt-3">
          {!d && !err && <div className="flex items-center gap-2 text-[12px] text-slate-500"><Loader2 className="h-4 w-4 animate-spin" />Crunching the ledger…</div>}
          {err && <p className="text-[12px] text-slate-500">Performance data is unavailable right now.</p>}
          {d && d.available === false && <p className="text-[12px] text-slate-500">{d.note || 'Not enough resolved forecasts to chart performance yet.'}</p>}

          {d && d.available && (
            <>
              {/* View selector — user portfolio vs model validation (never conflated) */}
              <div className="mb-3 inline-flex rounded-lg border border-slate-800 bg-slate-900/60 p-0.5 text-[11px]">
                <button onClick={() => setView('model')} className={`rounded-md px-2.5 py-1 font-semibold ${view === 'model' ? 'bg-violet-500/20 text-violet-200' : 'text-slate-400 hover:text-slate-200'}`}>Model performance</button>
                <button onClick={() => setView('portfolio')} className={`rounded-md px-2.5 py-1 font-semibold ${view === 'portfolio' ? 'bg-sky-500/20 text-sky-200' : 'text-slate-400 hover:text-slate-200'}`}>My portfolio</button>
              </div>

              {view === 'model' && (
                <>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
                    <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-3 rounded-sm bg-slate-400" />{d.benchmark?.label} <b className={pctColor(d.benchmark?.returnPct)}>{fmtPct(d.benchmark?.returnPct)}</b></span>
                    <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-3 rounded-sm bg-sky-400" />{m.label} <b className={pctColor(m.returnPct)}>{fmtPct(m.returnPct)}</b></span>
                  </div>
                  <DualSpark a={d.benchmark?.series} b={m.series} />
                  <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <Kpi label="Edge vs hold" value={fmtPct(d.edge?.vsBuyHoldPct)} tone={pctColor(d.edge?.vsBuyHoldPct)} />
                    <Kpi label="Sharpe" value={m.sharpe != null ? m.sharpe : 'n/a'} />
                    <Kpi label="Max drawdown" value={m.maxDrawdownPct != null ? fmtPct(m.maxDrawdownPct) : 'n/a'} tone="text-rose-300" />
                    <Kpi label="Profit factor" value={m.profitFactor != null ? m.profitFactor : 'n/a'} />
                    <Kpi label="Win rate" value={m.hitRate != null ? `${m.hitRate}%` : 'n/a'} sub={`n=${m.sampleSize}`} />
                    <Kpi label="Brier" value={m.brier != null ? m.brier : 'n/a'} />
                    <Kpi label="Fee drag" value={`-${Math.abs(m.feeDragPct || 0).toFixed(1)}%`} tone="text-amber-300" sub={`${m.trades} flips`} />
                    <Kpi label="Fee rate" value={`${m.feeRatePct}%`} sub="taker" />
                  </div>
                  <p className="mt-2 text-[10px] text-slate-500">Out-of-sample · {d.window?.from} → {d.window?.to} · {d.window?.n} resolved calls · model {m.modelVersion || '—'}</p>
                </>
              )}

              {view === 'portfolio' && (
                hasPortfolio ? (
                  <>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      <Kpi label="Equity" value={fmtUsd(pv.equity)} />
                      <Kpi label="Total return" value={pv.totalReturnPct != null ? fmtPct(pv.totalReturnPct) : 'n/a'} tone={pctColor(pv.totalReturnPct)} />
                      <Kpi label="Cash (USDC)" value={fmtUsd(pv.cash)} />
                      <Kpi label="Holdings" value={fmtUsd(pv.holdingsValue)} />
                      <Kpi label="Drawdown" value={pv.drawdownPct != null ? fmtPct(pv.drawdownPct) : (pv.historyReady ? 'n/a' : `collecting (${pv.historySampleCount || 0})`)} tone={pv.drawdownPct != null ? 'text-rose-300' : 'text-slate-400'} />
                      <Kpi label="Volatility" value={pv.volatilityPct != null ? `${pv.volatilityPct}%` : (pv.historyReady ? 'n/a' : `collecting (${pv.historySampleCount || 0})`)} />
                      <Kpi label={`${symbol} buy & hold`} value={fmtPct(d.benchmark?.returnPct)} sub="window ref" tone={pctColor(d.benchmark?.returnPct)} />
                      {pv.historyFrom && <Kpi label="Equity history" value={`${pv.historySampleCount || 0} days`} sub={`${pv.historyFrom} →`} />}
                    </div>
                    {(pv.allocation || []).length > 0 && (
                      <div className="mt-3">
                        <p className="mb-1.5 text-[10px] uppercase tracking-wide text-slate-500">Allocation</p>
                        <div className="space-y-1.5">
                          {pv.allocation.map((a, i) => (
                            <div key={i} className="flex items-center gap-2 text-[11px]">
                              <span className="w-12 shrink-0 font-semibold text-slate-300">{a.asset}</span>
                              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-sky-500" style={{ width: `${Math.max(2, Math.min(100, a.pct || 0))}%` }} /></div>
                              <span className="w-10 shrink-0 text-right font-mono text-slate-400">{a.pct != null ? `${a.pct}%` : '—'}</span>
                              <span className={`w-14 shrink-0 text-right font-mono ${pctColor(a.unrealizedPct)}`}>{a.unrealizedPct != null ? fmtPct(a.unrealizedPct) : '—'}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    <p className="mt-2 flex items-start gap-1 text-[10px] leading-relaxed text-slate-500"><Info className="mt-0.5 h-3 w-3 shrink-0" />{pv.note}</p>
                  </>
                ) : (
                  <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-[12px] text-slate-400"><Wallet className="h-4 w-4" />Sign in and add paper positions to see your portfolio performance here.</div>
                )
              )}

              <p className="mt-2 flex items-start gap-1 text-[9.5px] leading-relaxed text-slate-600"><Info className="mt-0.5 h-3 w-3 shrink-0" />{d.disclaimer}</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------------------------- root --------------------------------- */
export default function TraderHome({ symbol = 'BTC', onNav, params, onParams }) {
  const [d, setD] = React.useState(null);
  const [err, setErr] = React.useState(false);
  const horizon = params?.horizon || '7D';
  const focus = params?.focus || null;
  const perfOpen = focus === 'performance';
  const [flash, setFlash] = React.useState(null);

  const setHorizon = (h) => onParams && onParams((p) => ({ ...(p || {}), horizon: h }));
  const togglePerf = () => onParams && onParams((p) => ({ ...(p || {}), focus: (p?.focus === 'performance' ? null : 'performance') }));

  // Deep-link focus: scroll the target block into view and highlight it once.
  React.useEffect(() => {
    if (!focus || !d) return;
    const id = focus === 'performance' ? 'th-performance' : focus === 'projection' ? 'th-projection' : null;
    if (!id) return;
    setFlash(focus);
    const t1 = setTimeout(() => { const el = document.getElementById(id); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, 450);
    const t2 = setTimeout(() => setFlash(null), 3200);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [focus, d]);

  React.useEffect(() => {
    let alive = true;
    const pid = getPid();
    setD(null); setErr(false);
    fetch(`${API_BASE}/v1/albert/trader-home?pid=${encodeURIComponent(pid || '')}&symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => { if (!alive) return; if (j && (j.status === 'ready' || j.signal)) setD(j); else setErr(true); })
      .catch(() => { if (alive) setErr(true); });
    return () => { alive = false; };
  }, [symbol]);

  if (err) return null;
  if (!d) {
    return (
      <div className="mb-4 flex items-center gap-2 rounded-2xl border border-slate-800 bg-slate-950/40 p-6 text-[13px] text-slate-400">
        <Loader2 className="h-4 w-4 animate-spin" />Assembling your Trader Home…
      </div>
    );
  }

  const sig = d.signal || {};
  const tone = callTone(sig.call);
  const Tone = tone.Icon;
  const mkt = d.market || {};
  const conf = d.confluence;
  const edge = d.historicalEdge;
  const pi = d.portfolioImpact;
  const integ = d.integrity || {};
  const cb = sig.circuitBreaker;
  const cbActive = cb && (typeof cb === 'object' ? cb.active : String(cb).toLowerCase() !== 'normal');
  const up = (mkt.change24h || 0) >= 0;
  const briefPoints = (d.executiveBrief && d.executiveBrief.points) || [];

  return (
    <div className="mb-4 space-y-3">
      {/* 1) Signal + market — the 3-second read */}
      <div className={`rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 to-slate-950 p-4 ring-1 ${tone.ring}`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className={`flex h-11 w-11 items-center justify-center rounded-xl ${tone.bg} ${tone.fg}`}><Tone className="h-6 w-6" /></span>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-slate-500">{symbol} · engine call</p>
              <p className={`text-xl font-bold ${tone.fg}`}>{sig.call || 'Unavailable'}</p>
              <p className="text-[11px] text-slate-500">{sig.regime}{sig.confidence ? ` · ${sig.confidence} confidence` : ''}</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-lg font-bold text-white">{fmtUsd(mkt.price)}</p>
            <p className={`text-[12px] font-semibold ${up ? 'text-emerald-400' : 'text-rose-400'}`}>{up ? '+' : ''}{mkt.change24h ?? '\u2014'}% 24h</p>
            {sig.conviction != null && (
              <p className="mt-0.5 flex items-center justify-end gap-1 text-[10px] text-slate-500"><Gauge className="h-3 w-3" />Conviction {Math.round(sig.conviction)}/100</p>
            )}
          </div>
        </div>
        {cbActive && (
          <div className="mt-3 flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[11px] font-semibold text-amber-300"><AlertTriangle className="h-3.5 w-3.5" />Circuit breaker active</div>
        )}
      </div>

      {/* 2) Executive briefing — all points, deep-linked */}
      {briefPoints.length > 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><Activity className="h-3.5 w-3.5 text-sky-300" />Executive briefing</p>
          <div className="space-y-1.5">
            {briefPoints.map((pt, i) => {
              const route = briefingRoute(pt);
              return (
                <div key={i} className="flex items-start gap-2 text-[13px] leading-relaxed text-slate-200">
                  <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${i === 0 ? 'bg-sky-400' : 'bg-slate-600'}`} />
                  <span className="flex-1">{pt}
                    {route && onNav && (
                      <button onClick={() => onNav(route.section)} className="ml-1 inline-flex items-center gap-0.5 rounded bg-slate-800/70 px-1.5 py-0.5 text-[10px] font-semibold text-sky-300 hover:bg-slate-700/70">{route.label}<ArrowRight className="h-2.5 w-2.5" /></button>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
          {onNav && <button onClick={() => onNav('strategies')} className="mt-2.5 flex items-center gap-1 text-[11px] font-semibold text-sky-400 hover:text-sky-300">Open the Command Centre <ArrowRight className="h-3 w-3" /></button>}
        </div>
      )}

      {/* 3) Projection cone */}
      <ProjectionPanel projection={d.projection} symbol={symbol} selected={horizon} onSelect={setHorizon} highlight={flash === 'projection'} />

      {/* 4) Evidence: drivers + historical edge */}
      <div className="grid gap-3 md:grid-cols-2">
        {(d.drivers || []).length > 0 && (
          <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><Layers className="h-3.5 w-3.5 text-violet-300" />Drivers</p>
              {conf && <span className="text-[10px] text-slate-500">{conf.note}</span>}
            </div>
            <div className="space-y-2">
              {d.drivers.map((dr, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="w-28 shrink-0 truncate text-[12px] text-slate-300">{dr.label}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800">
                    <div className={`h-full rounded-full ${dr.direction === 'bullish' ? 'bg-emerald-500' : dr.direction === 'bearish' ? 'bg-rose-500' : 'bg-slate-500'}`} style={{ width: `${Math.max(4, Math.min(100, dr.score || 0))}%` }} />
                  </div>
                  <span className="w-8 shrink-0 text-right text-[11px] font-mono text-slate-400">{dr.score != null ? Math.round(dr.score) : '\u2014'}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {edge && (
          <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><ShieldCheck className="h-3.5 w-3.5 text-emerald-300" />Historical edge</p>
            <div className="grid grid-cols-2 gap-2 text-[12px]">
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2"><p className="text-slate-500">Brier</p><p className="font-mono text-slate-200">{edge.brier ?? '\u2014'}</p></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2"><p className="text-slate-500">Ann. Sharpe</p><p className="font-mono text-slate-200">{edge.sharpe ?? '\u2014'}</p></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2"><p className="text-slate-500">PSR</p><p className="font-mono text-slate-200">{edge.psr ?? '\u2014'}</p></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2"><p className="text-slate-500">Trades</p><p className="font-mono text-slate-200">{edge.nTrades ?? '\u2014'}</p></div>
            </div>
            <p className="mt-2 text-[10px] text-slate-600">{edge.note}</p>
            <button onClick={togglePerf} className="mt-2 flex items-center gap-1 text-[11px] font-semibold text-violet-300 hover:text-violet-200"><BarChart3 className="h-3.5 w-3.5" />{perfOpen ? 'Hide performance' : 'Open performance drill-down'} <ArrowRight className="h-3 w-3" /></button>
          </div>
        )}
      </div>

      {/* 5) Performance drill-down */}
      <PerformancePanel symbol={symbol} open={perfOpen} onToggle={togglePerf} highlight={flash === 'performance'} />

      {/* 6) Portfolio impact + integrity */}
      <div className="grid gap-3 md:grid-cols-2">
        {pi && (
          <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">Your portfolio</p>
            <div className="flex items-center justify-between text-[13px]">
              <span className="text-slate-400">Total value</span><span className="font-semibold text-white">{fmtUsd(pi.totalValue)}</span>
            </div>
            <div className="mt-1 flex items-center justify-between text-[13px]">
              <span className="text-slate-400">Protection</span>
              <span className={pi.protectionActive ? 'font-semibold text-amber-300' : 'text-slate-300'}>{pi.protectionActive ? 'Active' : 'Off'}{pi.drawdownPct != null ? ` · ${pi.drawdownPct}% dd` : ''}</span>
            </div>
            {!pi.symbolApproved && <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-300">{symbol} isn’t in your approved coins.</p>}
          </div>
        )}
        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><Clock className="h-3.5 w-3.5" />Data integrity</p>
          <div className="flex items-center gap-2 text-[12px]">
            {integ.stale ? <AlertTriangle className="h-4 w-4 text-amber-400" /> : <CheckCircle2 className="h-4 w-4 text-emerald-400" />}
            <span className={integ.stale ? 'text-amber-300' : 'text-slate-300'}>{integ.stale ? 'Some feeds are stale' : 'Feeds are fresh'}</span>
          </div>
          {integ.lastRun && <p className="mt-1 text-[10px] text-slate-600">Last full run: {new Date(integ.lastRun).toLocaleString()}</p>}
          <p className="mt-2 text-[10px] text-slate-600">Advisory / paper only — Albert explains the engine, he doesn’t place live trades.</p>
        </div>
      </div>
    </div>
  );
}
