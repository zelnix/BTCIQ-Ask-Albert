'use client';
// Market Driver Intelligence — the deterministic "who is moving Bitcoin" read.
// Consumes GET /api/v1/albert/market-driver/btc and renders: market posture,
// Albert's plain explanation, the driver attribution (first mover / current
// leader / confirming / resisting), the sequence, next-mover candidates,
// continuation & failure conditions, a data-quality indicator, and an on-demand
// evidence trace. Honest about observed vs inferred. Advisory / paper only.
import React from 'react';
import { API_BASE } from '../lib/api';
import {
  Loader2, TrendingUp, TrendingDown, Minus, Users, Crown, Flag, CheckCircle2,
  ShieldAlert, ArrowRightCircle, Activity, Gauge, ChevronDown, Info, AlertTriangle,
  Database, Radar, MessageCircle,
} from 'lucide-react';

const HORIZONS = ['INTRADAY', 'SWING', 'CYCLE'];
const humanize = (s) => (s || '').replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase());

const postureTone = (p) => {
  if (/STRONGLY_BULLISH/.test(p)) return { fg: 'text-emerald-300', bg: 'bg-emerald-500/15', ring: 'ring-emerald-500/40', Icon: TrendingUp };
  if (/BULLISH/.test(p)) return { fg: 'text-emerald-300', bg: 'bg-emerald-500/10', ring: 'ring-emerald-500/25', Icon: TrendingUp };
  if (/STRONGLY_BEARISH/.test(p)) return { fg: 'text-rose-300', bg: 'bg-rose-500/15', ring: 'ring-rose-500/40', Icon: TrendingDown };
  if (/BEARISH/.test(p)) return { fg: 'text-rose-300', bg: 'bg-rose-500/10', ring: 'ring-rose-500/25', Icon: TrendingDown };
  return { fg: 'text-slate-200', bg: 'bg-slate-500/10', ring: 'ring-slate-500/25', Icon: Minus };
};
const dirColor = (d) => (d === 'bullish' ? 'text-emerald-400' : d === 'bearish' ? 'text-rose-400' : 'text-slate-400');
const dqTone = (q) => ({
  VERIFIED: { fg: 'text-emerald-300', bg: 'bg-emerald-500/10', Icon: CheckCircle2 },
  STALE: { fg: 'text-amber-300', bg: 'bg-amber-500/10', Icon: AlertTriangle },
  CONFLICTING: { fg: 'text-amber-300', bg: 'bg-amber-500/10', Icon: AlertTriangle },
  MISSING: { fg: 'text-rose-300', bg: 'bg-rose-500/10', Icon: AlertTriangle },
}[q] || { fg: 'text-slate-300', bg: 'bg-slate-500/10', Icon: Info });

const evidenceBadge = (e) => {
  if (e === 'OBSERVED') return <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-300">observed</span>;
  if (e === 'STRONGLY_INFERRED') return <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[9px] font-semibold text-sky-300">inferred</span>;
  if (e === 'WEAKLY_INFERRED') return <span className="rounded bg-slate-500/15 px-1.5 py-0.5 text-[9px] font-semibold text-slate-400">weakly inferred</span>;
  return <span className="rounded bg-slate-500/15 px-1.5 py-0.5 text-[9px] font-semibold text-slate-500">unknown</span>;
};

// Colour-independent freshness indicator (dot + text label) — never colour alone.
const freshDot = { fresh: 'bg-emerald-400', delayed: 'bg-amber-400', stale: 'bg-rose-400', missing: 'bg-slate-500', conflicting: 'bg-amber-400' };
function FreshnessDot({ f }) {
  if (!f) return null;
  const age = f.ageHours != null ? (f.ageHours < 1 ? '<1h' : f.ageHours < 48 ? `${Math.round(f.ageHours)}h` : `${Math.round(f.ageHours / 24)}d`) : 'live';
  const title = `${f.label} · ${f.provider || 'source'} · ${f.marketTime ? String(f.marketTime).slice(0, 16) : ''}${f.tradingCalendarAware ? ' · trading-calendar aware' : ''}`;
  return (
    <span title={title} className="inline-flex items-center gap-1 text-[9px] font-semibold text-slate-400">
      <span className={`h-2 w-2 rounded-full ${freshDot[f.status] || 'bg-slate-500'}`} />
      {f.label}{f.ageHours != null ? ` · ${age}` : ''}
    </span>
  );
}

// Driver -> Ask Albert handoff: opens chat with a grounded question + the IMMUTABLE
// deterministic assessment (chain id, horizon, asOf, evidence + freshness). Albert
// explains it; he cannot alter it.
function askWhy(dv, role, meta) {
  if (!dv) return;
  const aged = dv.freshness && (dv.freshness.status === 'stale' || dv.freshness.status === 'missing');
  const q = `Why is ${humanize(dv.actor).toLowerCase()} ${humanize(dv.behavior).toLowerCase()} `
    + `${role} Bitcoin on the ${humanize(meta.horizon)} horizon? `
    + `Explain the observed vs inferred evidence and whether it's fresh.`
    + (aged ? ' (I know the reading may be stale — say so and offer to refresh.)' : '');
  const driver_context = {
    driverChainId: meta.driverChainId, engineVersion: meta.engineVersion,
    horizon: meta.horizon, asOf: meta.asOf, dataQuality: meta.dataQuality,
    role, actor: dv.actor, channel: dv.channel, behavior: dv.behavior, stage: dv.stage,
    evidenceStatus: dv.evidenceStatus, confidence: dv.confidence, detail: dv.detail,
    freshness: dv.freshness, sourceSnapshotIds: meta.sourceSnapshotIds,
  };
  try { window.dispatchEvent(new CustomEvent('albert:ask', { detail: { question: q, driver_context } })); } catch (e) { /* noop */ }
}

function AskWhyBtn({ dv, role, meta }) {
  return (
    <button onClick={(e) => { e.stopPropagation(); askWhy(dv, role, meta); }}
      className="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900/70 px-1.5 py-0.5 text-[9.5px] font-semibold text-sky-300 hover:border-sky-500/50 hover:text-sky-200">
      <MessageCircle className="h-3 w-3" />Ask why
    </button>
  );
}

function DriverCard({ d, icon: Icon, title, accent, role, meta }) {
  if (!d) return null;
  return (
    <div className={`rounded-xl border border-slate-800 bg-slate-950/50 p-3`}>
      <div className="mb-1.5 flex items-center justify-between">
        <span className={`flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider ${accent}`}><Icon className="h-3.5 w-3.5" />{title}</span>
        {evidenceBadge(d.evidenceStatus)}
      </div>
      <p className="text-[14px] font-bold text-white">{humanize(d.actor)}</p>
      <p className={`text-[12px] font-semibold ${dirColor(d.direction)}`}>{humanize(d.behavior)} · {humanize(d.stage)}</p>
      <p className="mt-1 text-[11px] text-slate-400">via {humanize(d.channel)}</p>
      {d.detail && <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">{d.detail}</p>}
      <div className="mt-2 flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800">
          <div className="h-full rounded-full bg-sky-500" style={{ width: `${Math.round((d.confidence || 0) * 100)}%` }} />
        </div>
        <span className="text-[10px] font-mono text-slate-400">{Math.round((d.confidence || 0) * 100)}%</span>
      </div>
      <div className="mt-2 flex items-center justify-between">
        <FreshnessDot f={d.freshness} />
        <AskWhyBtn dv={d} role={role || 'driving'} meta={meta} />
      </div>
    </div>
  );
}

function DriverRow({ d, side, meta }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-2.5 py-1.5">
      {side === 'confirm' ? <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-400" /> : <ShieldAlert className="h-3.5 w-3.5 shrink-0 text-rose-400" />}
      <span className="text-[12px] font-semibold text-slate-200">{humanize(d.actor)}</span>
      <span className={`text-[11px] ${dirColor(d.direction)}`}>{humanize(d.behavior)}</span>
      <FreshnessDot f={d.freshness} />
      <div className="ml-auto flex items-center gap-2">
        <span className="text-[10px] text-slate-500">{humanize(d.stage)} · {Math.round((d.confidence || 0) * 100)}%</span>
        <AskWhyBtn dv={d} role={side === 'confirm' ? 'confirming' : 'resisting'} meta={meta} />
      </div>
    </div>
  );
}

function TracePanel({ horizon }) {
  const [open, setOpen] = React.useState(false);
  const [t, setT] = React.useState(null);
  React.useEffect(() => {
    if (!open || t) return;
    fetch(`${API_BASE}/v1/albert/market-driver/btc/trace?horizon=${horizon}`, { cache: 'no-store' })
      .then((r) => r.json()).then((j) => setT(j)).catch(() => setT({ status: 'error' }));
  }, [open, horizon]); // eslint-disable-line
  React.useEffect(() => { setT(null); }, [horizon]);
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between">
        <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><Database className="h-3.5 w-3.5 text-violet-300" />Evidence &amp; rule trace</span>
        <ChevronDown className={`h-4 w-4 text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="mt-3">
          {!t && <div className="flex items-center gap-2 text-[12px] text-slate-500"><Loader2 className="h-4 w-4 animate-spin" />Loading trace…</div>}
          {t && t.status === 'error' && <p className="text-[12px] text-slate-500">Trace unavailable.</p>}
          {t && t.status === 'ready' && (
            <>
              <p className="mb-2 text-[10px] text-slate-500">Chain {t.driverChainId} · engine {t.engineVersion}</p>
              <div className="space-y-1.5">
                {(t.drivers || []).map((d, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    <span className="w-24 shrink-0 font-semibold text-slate-300">{humanize(d.actor)}</span>
                    {evidenceBadge(d.evidenceStatus)}
                    <span className={`${dirColor(d.direction)}`}>{humanize(d.behavior)}</span>
                    <span className="ml-auto font-mono text-slate-400">{d.contribution > 0 ? '+' : ''}{d.contribution}</span>
                  </div>
                ))}
              </div>
              {(t.snapshots || []).length > 0 && (
                <div className="mt-3 border-t border-slate-800 pt-2">
                  <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">Source snapshots</p>
                  {t.snapshots.map((s, i) => (
                    <p key={i} className="text-[10px] text-slate-500">{s.id} · {s.source || '—'} · {s.quality} {s.asOf ? `· ${String(s.asOf).slice(0, 16)}` : ''}</p>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function MarketDrivers({ horizon = 'SWING', onHorizon }) {
  const [d, setD] = React.useState(null);
  const [err, setErr] = React.useState(false);
  const hz = HORIZONS.includes(horizon) ? horizon : 'SWING';

  React.useEffect(() => {
    let alive = true;
    setD(null); setErr(false);
    fetch(`${API_BASE}/v1/albert/market-driver/btc?horizon=${hz}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => { if (!alive) return; if (j && j.status === 'ready') setD(j); else setErr(true); })
      .catch(() => { if (alive) setErr(true); });
    return () => { alive = false; };
  }, [hz]);

  const tone = d ? postureTone(d.marketPosture) : postureTone('');
  const Tone = tone.Icon;
  const dq = d ? dqTone(d.dataQuality) : dqTone('');
  const DQIcon = dq.Icon;
  const meta = d ? { driverChainId: d.driverChainId, engineVersion: d.engineVersion, horizon: hz, asOf: d.asOf, dataQuality: d.dataQuality, sourceSnapshotIds: d.sourceSnapshotIds } : {};

  return (
    <div className="space-y-4">
      {/* Header + horizon selector */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-bold text-white"><Users className="h-5 w-5 text-sky-300" />Market Drivers</h2>
          <p className="mt-0.5 text-[12px] text-slate-400">Who is actually moving Bitcoin — and who could rotate in next.</p>
        </div>
        <div className="inline-flex rounded-lg border border-slate-800 bg-slate-900/60 p-0.5 text-[11px]">
          {HORIZONS.map((h) => (
            <button key={h} onClick={() => onHorizon && onHorizon(h)}
              className={`rounded-md px-3 py-1.5 font-semibold ${h === hz ? 'bg-sky-500/20 text-sky-200' : 'text-slate-400 hover:text-slate-200'}`}>{humanize(h)}</button>
          ))}
        </div>
      </div>

      {err && <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-6 text-[13px] text-slate-400">Market driver intelligence is unavailable right now.</div>}
      {!d && !err && (
        <div className="flex items-center gap-2 rounded-2xl border border-slate-800 bg-slate-950/40 p-6 text-[13px] text-slate-400"><Loader2 className="h-4 w-4 animate-spin" />Reading the tape…</div>
      )}

      {d && (
        <>
          {/* Posture summary */}
          <div className={`rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 to-slate-950 p-4 ring-1 ${tone.ring}`}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className={`flex h-12 w-12 items-center justify-center rounded-xl ${tone.bg} ${tone.fg}`}><Tone className="h-6 w-6" /></span>
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">BTC · {humanize(hz)} posture</p>
                  <p className={`text-xl font-bold ${tone.fg}`}>{humanize(d.marketPosture)}</p>
                  <p className="text-[11px] text-slate-500">Regime: {humanize(d.regime)}</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-center">
                  <p className="text-[9px] uppercase tracking-wide text-slate-500">Score</p>
                  <p className="text-2xl font-bold text-white">{d.score}<span className="text-sm text-slate-500">/100</span></p>
                </div>
                <div className="text-center">
                  <p className="text-[9px] uppercase tracking-wide text-slate-500">Confidence</p>
                  <p className="flex items-center gap-1 text-lg font-bold text-slate-200"><Gauge className="h-4 w-4" />{Math.round((d.confidence || 0) * 100)}%</p>
                </div>
                <div className={`flex items-center gap-1.5 rounded-lg ${dq.bg} px-2.5 py-1.5 text-[11px] font-semibold ${dq.fg}`}>
                  <DQIcon className="h-3.5 w-3.5" />{humanize(d.dataQuality)}
                </div>
              </div>
            </div>
            {/* score bar */}
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800">
              <div className={`h-full rounded-full ${d.score >= 58 ? 'bg-emerald-500' : d.score > 42 ? 'bg-slate-500' : 'bg-rose-500'}`} style={{ width: `${d.score}%` }} />
            </div>
          </div>

          {/* Albert's plain explanation */}
          {d.explanation && (
            <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
              <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><Activity className="h-3.5 w-3.5 text-sky-300" />Albert’s read</p>
              <p className="text-[13px] leading-relaxed text-slate-200">{d.explanation}</p>
            </div>
          )}

          {/* Attribution: first mover + current leader */}
          <div className="grid gap-3 md:grid-cols-2">
            <DriverCard d={d.firstMover} icon={Flag} title="First mover" accent="text-sky-300" role="leading" meta={meta} />
            <DriverCard d={d.currentLeader} icon={Crown} title="Current leader" accent="text-amber-300" role="leading" meta={meta} />
          </div>

          {/* Sequence + confirming/resisting */}
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
              <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-300" />Confirming drivers</p>
              <div className="space-y-1.5">
                {(d.confirmingDrivers || []).length ? d.confirmingDrivers.map((x, i) => <DriverRow key={i} d={x} side="confirm" meta={meta} />) : <p className="text-[12px] text-slate-500">None strong enough to list.</p>}
              </div>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
              <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><ShieldAlert className="h-3.5 w-3.5 text-rose-300" />Resisting drivers</p>
              <div className="space-y-1.5">
                {(d.resistingDrivers || []).length ? d.resistingDrivers.map((x, i) => <DriverRow key={i} d={x} side="resist" meta={meta} />) : <p className="text-[12px] text-slate-500">No meaningful pushback right now.</p>}
              </div>
            </div>
          </div>

          {/* Next mover candidates */}
          {(d.nextMoverCandidates || []).length > 0 && (
            <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
              <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><ArrowRightCircle className="h-3.5 w-3.5 text-violet-300" />Who could move next</p>
              <div className="grid gap-2 sm:grid-cols-3">
                {d.nextMoverCandidates.map((n, i) => (
                  <div key={i} className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                    <div className="flex items-center justify-between">
                      <p className="text-[13px] font-bold text-white">{humanize(n.actor)}</p>
                      <span className={`rounded px-1.5 py-0.5 text-[9px] font-semibold ${n.probabilityBand === 'HIGH' ? 'bg-emerald-500/15 text-emerald-300' : n.probabilityBand === 'MEDIUM' ? 'bg-amber-500/15 text-amber-300' : 'bg-slate-500/15 text-slate-400'}`}>{n.probabilityBand} odds</span>
                    </div>
                    <p className="text-[10px] text-slate-500">{humanize(n.stage)}</p>
                    <p className="mt-1 text-[11px] leading-relaxed text-slate-400">If {n.condition}.</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Continuation / failure */}
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.04] p-4">
              <p className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-emerald-300"><TrendingUp className="h-3.5 w-3.5" />This continues if…</p>
              <p className="text-[12px] leading-relaxed text-slate-300">{d.continuationCondition}</p>
            </div>
            <div className="rounded-2xl border border-rose-500/20 bg-rose-500/[0.04] p-4">
              <p className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-rose-300"><TrendingDown className="h-3.5 w-3.5" />It breaks if…</p>
              <p className="text-[12px] leading-relaxed text-slate-300">{d.failureCondition}</p>
            </div>
          </div>

          {/* Evidence trace */}
          <TracePanel horizon={hz} />

          <p className="flex items-start gap-1 text-[10px] leading-relaxed text-slate-600">
            <Info className="mt-0.5 h-3 w-3 shrink-0" />
            {d.engineVersion} · {d.sequenceStage ? `sequence ${humanize(d.sequenceStage)} · ` : ''}Custody is not ownership; ETF shares and exchange balances can represent many actors. Market intelligence proposes posture — your portfolio rules decide any action and size. Advisory / paper only.
          </p>
        </>
      )}
    </div>
  );
}
