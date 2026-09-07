'use client';
import React from 'react';
import { API_BASE, getPid } from '../lib/api';
import { Activity, ArrowRight, Info, X, Loader2 } from 'lucide-react';

// Self-contained read-only Decision Journey modal (Phase H replay). Shared so the
// Discovery Feed can open a coin's journey directly. Renders the deterministic
// lifecycle assembled by GET /api/v1/albert/lifecycle/{asset}. Never recomputes.

const fmt = (n) => (n == null || isNaN(n)) ? '—' : '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
const fmtX = (n) => (n == null || isNaN(n)) ? '—' : '$' + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const qty = (n) => (n == null || isNaN(n)) ? '—' : Number(n).toLocaleString(undefined, { maximumFractionDigits: 8 });
const fmtTs = (t) => { try { return t ? new Date(t).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'; } catch { return t || '—'; } };

const REASON_LABEL = {
  EMERGENCY_EXIT: 'Emergency exit', PORTFOLIO_DRAWDOWN_RISK: 'Portfolio drawdown risk', THESIS_INVALIDATION: 'Thesis invalidated', RISK_REDUCTION: 'Risk reduction',
  REBALANCE: 'Rebalance', PROFIT_TAKE: 'Profit-take', OPPORTUNITY_ENTRY: 'Opportunity entry',
  THESIS_INTACT: 'Thesis intact', BELOW_ENTRY_LINE: 'Below entry line', GATED_BY_MANDATE: 'Gated by mandate',
  GATED_BY_DRAWDOWN: 'Gated by drawdown protection', STALE_DATA: 'Stale data', NO_HEADROOM: 'No room to add',
};
const STAGE_COLOR = {
  WAIT: 'bg-slate-700/40 text-slate-300 border-slate-600',
  BUY: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  ADD: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  HOLD: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
  TRIM: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  SELL: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
};
const OSTATE_COLOR = {
  DRAFT: 'text-slate-400', PENDING_CONFIRMATION: 'text-amber-300', CONFIRMED: 'text-sky-300',
  WORKING: 'text-sky-300', PARTIALLY_FILLED: 'text-violet-300', FILLED: 'text-emerald-300',
  CANCELLED: 'text-slate-400', REJECTED: 'text-rose-300', EXPIRED: 'text-slate-500',
};

function FlipConditions({ items }) {
  if (!items || !items.length) return <p className="text-[11px] text-slate-500">No flip conditions.</p>;
  return (
    <ul className="space-y-1">
      {items.map((f, i) => {
        const sell = String(f.toCall).startsWith('SELL');
        return (
          <li key={i} className="flex items-start gap-1.5 text-[11px] text-slate-300">
            <span className={`mt-0.5 shrink-0 rounded border px-1 py-0.5 text-[9px] font-bold ${sell ? 'border-rose-500/40 text-rose-300' : f.toCall === 'BUY' ? 'border-emerald-500/40 text-emerald-300' : 'border-slate-600 text-slate-400'}`}>→ {String(f.toCall).replace('SELL:', 'SELL/')}</span>
            <span>{f.detail}</span>
          </li>
        );
      })}
    </ul>
  );
}

function JourneyNode({ ev, isLast }) {
  const [open, setOpen] = React.useState(false);
  const orders = ev.orders || [];
  return (
    <div className="relative pl-6">
      {!isLast && <div className="absolute left-[9px] top-7 h-[calc(100%-1rem)] w-px bg-slate-700" />}
      <div className={`absolute left-1 top-2 h-3.5 w-3.5 rounded-full border-2 ${ev.portfolioRiskIntervention ? 'border-rose-500 bg-rose-900' : 'border-slate-600 bg-slate-900'}`} />
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between gap-2 py-1.5 text-left">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${STAGE_COLOR[ev.stage] || STAGE_COLOR.WAIT}`}>{ev.stage}</span>
          <span className="text-[12px] font-semibold text-white">{ev.label}</span>
          {ev.portfolioRiskIntervention && <span className="rounded-full border border-rose-500/40 px-1.5 py-0.5 text-[9px] text-rose-300">drawdown</span>}
          {ev.hasExecution ? <span className="rounded-full border border-emerald-500/40 px-1.5 py-0.5 text-[9px] text-emerald-300">filled</span> : null}
        </div>
        <span className="shrink-0 text-[10px] text-slate-500">{fmtTs(ev.timestamp)}</span>
      </button>
      {open && (
        <div className="mb-2 space-y-2 rounded-lg border border-slate-800 bg-slate-950/50 p-2.5 text-[11px]">
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-slate-400">
            <span>Regime <b className="text-slate-200">{ev.regime || '—'}</b></span>
            <span>Score <b className="text-slate-200">{ev.score ?? '—'}</b></span>
            <span>Conf <b className="text-slate-200">{ev.confidence != null ? ev.confidence + '%' : '—'}</b></span>
            {ev.previousCall && <span>{ev.previousCall} <ArrowRight className="inline h-3 w-3" /> <b className="text-slate-200">{ev.call}</b></span>}
          </div>
          {ev.reasonCode && <p className="text-slate-300">Reason: <span className="text-slate-200">{REASON_LABEL[ev.reasonCode] || ev.reasonCode}</span></p>}
          {(ev.changeReason && ev.changeReason.length > 0) && <p className="text-slate-500">Changed because: {ev.changeReason.join('; ')}.</p>}
          {ev.portfolioRiskNote && <p className="text-rose-300">⚠ {ev.portfolioRiskNote}</p>}
          <div className="rounded border border-slate-800 bg-slate-900/40 p-2">
            <p className="mb-0.5 text-[9px] uppercase tracking-wide text-violet-300">Decision (recommended)</p>
            <p className="text-slate-300">Δ {ev.recommendedDeltaUsd != null ? fmtX(ev.recommendedDeltaUsd) : '—'}
              {ev.positionBefore && ev.positionAfter && <span className="text-slate-500"> · position {fmtX(ev.positionBefore.valueUsd)} ({ev.positionBefore.pct}%) <ArrowRight className="inline h-3 w-3" /> {fmtX(ev.positionAfter.valueUsd)} ({ev.positionAfter.pct}%)</span>}</p>
          </div>
          <div className="rounded border border-slate-800 bg-slate-900/40 p-2">
            <p className="mb-0.5 text-[9px] uppercase tracking-wide text-sky-300">Execution (paper order)</p>
            {orders.length === 0 ? <p className="text-slate-500">No paper order created for this decision.</p> : orders.map((o) => (
              <div key={o.orderIntentId} className="text-slate-300">
                <span className={`font-semibold ${OSTATE_COLOR[o.state] || 'text-slate-300'}`}>{o.state}</span> · {o.side} {fmtX(o.amountUsd)}
                {o.fills && o.fills.length > 0 ? <span className="text-emerald-300"> · {o.fills.length} fill{o.fills.length > 1 ? 's' : ''} ({o.fills.map((f) => qty(f.quantity) + '@' + fmtX(f.price)).join(', ')})</span> : <span className="text-slate-500"> · no fill</span>}
              </div>
            ))}
          </div>
          <div className="rounded border border-slate-800 bg-slate-900/40 p-2">
            <p className="mb-0.5 text-[9px] uppercase tracking-wide text-emerald-300">Portfolio effect (paper exposure)</p>
            <p className="text-slate-300">Paper position at this point: <b className="text-white">{qty(ev.paperPositionSizeAtDecision)}</b> units</p>
          </div>
          {(ev.flipConditions && ev.flipConditions.length > 0) && (
            <div><p className="mb-0.5 flex items-center gap-1 text-[9px] uppercase text-slate-500"><Info className="h-3 w-3" />What would change this</p><FlipConditions items={ev.flipConditions} /></div>
          )}
          <p className="text-[9px] text-slate-600">snapshot {String(ev.snapshotId || '').slice(0, 8)} · engine {ev.engineVersion} · hash {String(ev.decisionInputsHash || '').slice(0, 10)}</p>
        </div>
      )}
    </div>
  );
}

export default function JourneyModal({ asset, onClose }) {
  const [lc, setLc] = React.useState(null);
  const [err, setErr] = React.useState('');
  React.useEffect(() => {
    const pid = getPid();
    fetch(`${API_BASE}/v1/albert/lifecycle/${encodeURIComponent(asset)}?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' })
      .then((r) => r.json()).then(setLc).catch(() => setErr('Could not load journey'));
  }, [asset]);
  const events = lc?.events || [];
  const isEmpty = lc && (lc.status === 'empty' || (lc.status === 'ready' && events.length === 0));
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900 p-4" onClick={(e) => e.stopPropagation()}>
        <div className="mb-2 flex items-center justify-between">
          <h4 className="flex items-center gap-2 text-sm font-bold text-white"><Activity className="h-4 w-4 text-sky-300" />{asset} — Decision Journey</h4>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X className="h-4 w-4" /></button>
        </div>
        {!lc && !err && <div className="flex items-center gap-2 py-6 text-[12px] text-slate-400"><Loader2 className="h-3.5 w-3.5 animate-spin" />Loading journey…</div>}
        {err && <p className="py-6 text-center text-[12px] text-rose-400">{err}</p>}
        {isEmpty && (
          <div className="py-8 text-center">
            <Activity className="mx-auto mb-2 h-6 w-6 text-slate-600" />
            <p className="text-[13px] font-semibold text-slate-300">No journey yet for {asset}</p>
            <p className="mx-auto mt-1 max-w-xs text-[11px] text-slate-500">Albert hasn&apos;t made a tracked decision on {asset} yet. A journey builds as its call changes over time (WAIT → BUY → ADD → HOLD → TRIM → SELL).</p>
          </div>
        )}
        {lc && lc.status === 'ready' && events.length > 0 && (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-slate-800 bg-slate-950/50 p-2.5 text-[11px]">
              <span className="text-slate-500">Current paper exposure</span>
              <b className={lc.currentPaperPositionSize > 0 ? 'text-emerald-300' : 'text-slate-400'}>{qty(lc.currentPaperPositionSize)} units</b>
              <span className="text-slate-600">· {lc.eventCount} decision{lc.eventCount === 1 ? '' : 's'} · engine {lc.currentEngineVersion}</span>
            </div>
            <div className="space-y-0">
              {events.map((ev, i) => <JourneyNode key={ev.eventId || i} ev={ev} isLast={i === events.length - 1} />)}
            </div>
            <p className="mt-3 text-[10px] text-slate-600">Read-only replay of frozen snapshots — each node shows its original engine version. History is never recomputed.</p>
          </>
        )}
      </div>
    </div>
  );
}
