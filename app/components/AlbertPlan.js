'use client';

import React from 'react';
import { API_BASE, getPid } from '../lib/api';
import { Button } from '@/components/ui/button';
import { ShieldCheck, Wallet, Target, Plus, Trash2, Loader2, Check, ChevronDown, Info, History, MessageCircle, ArrowRight, X, Layers, AlertTriangle } from 'lucide-react';

const fmt = (n) => (n == null || isNaN(n)) ? '—' : '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
// Exact (2dp) formatter — SELL amounts must be shown to the cent, never recomputed on the client.
const fmtX = (n) => (n == null || isNaN(n)) ? '—' : '$' + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const qty = (n) => (n == null || isNaN(n)) ? '—' : Number(n).toLocaleString(undefined, { maximumFractionDigits: 8 });

const REASON_LABEL = {
  EMERGENCY_EXIT: 'Emergency exit', THESIS_INVALIDATION: 'Thesis invalidated', RISK_REDUCTION: 'Risk reduction',
  REBALANCE: 'Rebalance', PROFIT_TAKE: 'Profit-take', OPPORTUNITY_ENTRY: 'Opportunity entry',
  THESIS_INTACT: 'Thesis intact', BELOW_ENTRY_LINE: 'Below entry line', GATED_BY_MANDATE: 'Gated by mandate',
  STALE_DATA: 'Stale data', NO_HEADROOM: 'No room to add',
};
const INELIG_LABEL = {
  EXCLUDED_BY_MANDATE: 'Excluded by mandate', NOT_IN_APPROVED_UNIVERSE: 'Not in approved universe',
  MANDATE_INCOMPLETE: 'Mandate incomplete', STALE_DATA: 'Stale market data',
};

function ActionPill({ a, big }) {
  const map = { BUY: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40', HOLD: 'bg-sky-500/15 text-sky-300 border-sky-500/40', SELL: 'bg-rose-500/15 text-rose-300 border-rose-500/40', WAIT: 'bg-slate-700/40 text-slate-300 border-slate-600' };
  const size = big ? 'px-2.5 py-1 text-[12px] font-extrabold tracking-wide' : 'px-2 py-0.5 text-[10px] font-bold';
  return <span className={`rounded-full border ${size} ${map[a] || map.WAIT}`}>{a}</span>;
}

// SELL trim vs full-exit must be unmistakable — plain language first.
function SellActionPill({ p }) {
  if (!p) return null;
  const exit = p.action === 'EXIT_100';
  const label = exit ? 'Exit 100%' : 'Trim ' + p.action.replace('TRIM_', '') + '%';
  return <span className={`rounded-full border px-1.5 py-0.5 text-[10px] font-bold ${exit ? 'bg-rose-600/25 text-rose-200 border-rose-500/60' : 'bg-amber-500/15 text-amber-300 border-amber-500/40'}`}>{label}</span>;
}

function EligibilityChip({ d }) {
  if (d.eligible) return null;
  return (
    <span title={INELIG_LABEL[d.ineligibilityReason] || d.ineligibilityReason} className="inline-flex items-center gap-0.5 rounded-full border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-semibold text-amber-300">
      <AlertTriangle className="h-2.5 w-2.5" />INELIGIBLE
    </span>
  );
}

// Recommendation cell: exact backend numbers only — never recomputed here.
function CallCell({ d }) {
  if (d.action === 'BUY') return <span className="text-emerald-400">{fmt(d.recommendedDeployNowUsd)} now <span className="text-slate-600">/ {fmt(d.totalPlannedDeploymentUsd)} planned</span></span>;
  if (d.action === 'SELL' && d.sellPlan) return <span className="text-rose-300">{fmtX(d.sellPlan.sellUsd)} <span className="text-slate-500">({qty(d.sellPlan.sellQty)} {d.symbol})</span></span>;
  if (d.action === 'HOLD') return <span className="text-sky-300">Hold — no change</span>;
  return <span className="text-slate-500">Wait</span>;
}

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

function precedenceRank(reasonCode, order) { return (order || {})[reasonCode]; }

// Read-only explanation modal. The deterministic call visually dominates; Albert's
// prose is clearly secondary and CANNOT change any number.
function ExplainModal({ decision, onClose }) {
  const [loading, setLoading] = React.useState(true);
  const [text, setText] = React.useState('');
  const [err, setErr] = React.useState('');
  React.useEffect(() => {
    let alive = true;
    setLoading(true); setText(''); setErr('');
    fetch(`${API_BASE}/v1/albert/explain-call`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pid: getPid(), decisionId: decision.decisionId, asset: decision.symbol, decision, question: 'Why this call, why this amount, and what would change it?' }) })
      .then((r) => r.json()).then((j) => { if (!alive) return; setText(j.explanation || ''); if (!j.explanation) setErr(j.error || 'No explanation returned.'); })
      .catch(() => { if (alive) setErr('Could not reach Albert.'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [decision]);
  const d = decision;
  return (
    <div className="fixed inset-0 z-[120] flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div className="max-h-[88vh] w-full max-w-lg overflow-y-auto rounded-t-2xl border border-slate-700 bg-slate-950 p-4 sm:rounded-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-base font-bold text-white">{d.symbol}</span>
            <ActionPill a={d.action} />
            {d.action === 'SELL' && <SellActionPill p={d.sellPlan} />}
            <EligibilityChip d={d} />
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-200"><X className="h-4 w-4" /></button>
        </div>
        {/* DETERMINISTIC FACTS — the source of truth, always dominant */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3 text-[12px]">
          <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
            <div><span className="text-slate-500">Reason</span><div className="font-semibold text-slate-200">{REASON_LABEL[d.reasonCode] || d.reasonCode}</div></div>
            <div><span className="text-slate-500">Precedence</span><div className="font-semibold text-slate-200">{d.precedenceRuleApplied}</div></div>
            <div><span className="text-slate-500">Opportunity score</span><div className="font-semibold text-slate-200">{d.opportunityScore}</div></div>
            <div><span className="text-slate-500">Confidence</span><div className="font-semibold text-slate-200">{d.confidence}%</div></div>
            {d.action === 'BUY' && <div className="col-span-2"><span className="text-slate-500">Deploy now / planned</span><div className="font-semibold text-emerald-400">{fmt(d.recommendedDeployNowUsd)} / {fmt(d.totalPlannedDeploymentUsd)}</div></div>}
            {d.action === 'SELL' && d.sellPlan && <div className="col-span-2"><span className="text-slate-500">Sell</span><div className="font-semibold text-rose-300">{d.sellPlan.action.replace('_', ' ')} · {fmtX(d.sellPlan.sellUsd)} · {qty(d.sellPlan.sellQty)} {d.symbol}</div></div>}
            {d.positionBefore && <div className="col-span-2 text-[11px] text-slate-400">Position: {fmtX(d.positionBefore.valueUsd)} ({d.positionBefore.pct}%) <ArrowRight className="inline h-3 w-3" /> {fmtX((d.positionAfter || {}).valueUsd)} ({(d.positionAfter || {}).pct}%)</div>}
            {d.invalidation ? <div className="col-span-2 text-[11px] text-rose-400">Invalidation ≈ {fmtX(d.invalidation)}</div> : null}
          </div>
          {!d.eligible && <p className="mt-2 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300">Ineligible — {INELIG_LABEL[d.ineligibilityReason] || d.ineligibilityReason}. This can never be a BUY until that clears.</p>}
        </div>
        {/* ALBERT'S PROSE — explicitly secondary + read-only */}
        <div className="mt-3">
          <p className="mb-1 flex items-center gap-1 text-[10px] uppercase tracking-wide text-violet-300"><MessageCircle className="h-3 w-3" />Albert&apos;s explanation (read-only)</p>
          {loading ? <div className="flex items-center gap-2 text-[12px] text-slate-400"><Loader2 className="h-3.5 w-3.5 animate-spin" />Albert is reading the snapshot…</div>
            : err ? <p className="text-[12px] text-slate-500">{err}</p>
            : <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-slate-300">{text}</p>}
          <p className="mt-2 text-[10px] text-slate-600">Albert explains the numbers above — he cannot change the call, amount, score, or invalidation.</p>
        </div>
      </div>
    </div>
  );
}

function HistoryDrawer({ asset, onClose }) {
  const [rows, setRows] = React.useState(null);
  React.useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/v1/albert/decision-history?pid=${encodeURIComponent(getPid())}&asset=${encodeURIComponent(asset)}&limit=50`, { cache: 'no-store' })
      .then((r) => r.json()).then((j) => { if (alive) setRows(j.events || []); }).catch(() => { if (alive) setRows([]); });
    return () => { alive = false; };
  }, [asset]);
  return (
    <div className="fixed inset-0 z-[120] flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div className="max-h-[88vh] w-full max-w-lg overflow-y-auto rounded-t-2xl border border-slate-700 bg-slate-950 p-4 sm:rounded-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <p className="flex items-center gap-2 text-base font-bold text-white"><History className="h-4 w-4 text-sky-300" />{asset} — decision history</p>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-200"><X className="h-4 w-4" /></button>
        </div>
        {rows == null ? <div className="flex items-center gap-2 text-[12px] text-slate-400"><Loader2 className="h-3.5 w-3.5 animate-spin" />Loading…</div>
          : rows.length === 0 ? <p className="text-[12px] text-slate-500">No call changes recorded yet. The advice for {asset} has been stable.</p>
          : (
            <ol className="relative space-y-3 border-l border-slate-800 pl-4">
              {rows.map((ev, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-sky-500" />
                  <p className="text-[12px] font-semibold text-slate-200">{ev.headline || ev.changeType}</p>
                  <p className="text-[10px] text-slate-500">{new Date(ev.changedAt).toLocaleString()}</p>
                  <ul className="mt-0.5 space-y-0.5">{(ev.changeReason || []).map((r, j) => <li key={j} className="text-[11px] text-slate-400">• {r}</li>)}</ul>
                  <p className="mt-0.5 text-[9px] text-slate-600" title={`prev ${ev.previousSnapshotId} → new ${ev.newSnapshotId}`}>snapshot {String(ev.previousSnapshotId || '').slice(0, 8)} → {String(ev.newSnapshotId || '').slice(0, 8)}</p>
                </li>
              ))}
            </ol>
          )}
        <p className="mt-3 text-[10px] text-slate-600">Each entry links the previous and new immutable decision snapshots — a full audit trail of why the advice changed.</p>
      </div>
    </div>
  );
}

function RegimeBanner({ reg, buyThresh, pool }) {
  const color = reg.regime === 'BULL' ? 'text-emerald-400' : reg.regime === 'BEAR' ? 'text-rose-400' : 'text-amber-400';
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-bold"><span className="text-slate-400">Market Regime: </span><span className={color}>{reg.regime}</span> <span className="text-[11px] font-normal text-slate-500">— {reg.confidence}% confidence</span></p>
        <p className="text-[11px] text-slate-500">BUY line ≥ {buyThresh} · deploy pool {fmt(pool)}</p>
      </div>
      <p className="mt-0.5 text-[11px] text-slate-400">{(reg.reasons || []).join('; ')}.</p>
    </div>
  );
}

function Stat({ label, value, sub, accent }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
      <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-0.5 text-lg font-bold ${accent || 'text-white'}`}>{value}</p>
      {sub && <p className="text-[10px] text-slate-500">{sub}</p>}
    </div>
  );
}

export default function AlbertPlan() {
  const [summary, setSummary] = React.useState(null);
  const [mandate, setMandate] = React.useState(null);
  const [complete, setComplete] = React.useState(false);
  const [decisions, setDecisions] = React.useState(null);
  const [expanded, setExpanded] = React.useState(null);
  const [explainFor, setExplainFor] = React.useState(null);
  const [historyFor, setHistoryFor] = React.useState(null);
  const [openMandate, setOpenMandate] = React.useState(false);
  const [openPortfolio, setOpenPortfolio] = React.useState(false);
  const [savingM, setSavingM] = React.useState(false);
  const [savingP, setSavingP] = React.useState(false);
  const [usdc, setUsdc] = React.useState('');
  const [positions, setPositions] = React.useState([]);

  const load = React.useCallback(async () => {
    const pid = getPid();
    try {
      const [mr, sr, pr] = await Promise.all([
        fetch(`${API_BASE}/v1/albert/mandate?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' }).then((r) => r.json()),
        fetch(`${API_BASE}/v1/albert/portfolio-summary?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' }).then((r) => r.json()),
        fetch(`${API_BASE}/v1/portfolio?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' }).then((r) => r.json()),
      ]);
      setMandate(mr.mandate); setComplete(mr.complete); setSummary(sr);
      setUsdc(pr.usdc != null ? String(pr.usdc) : '');
      setPositions((pr.positions || []).map((p) => ({ asset: p.asset || '', size: p.size ?? '', avg_entry: p.avg_entry ?? '' })));
      fetch(`${API_BASE}/v1/albert/decisions?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' }).then((r) => r.json()).then(setDecisions).catch(() => {});
    } catch (e) { /* noop */ }
  }, []);
  React.useEffect(() => { load(); }, [load]);

  const saveMandate = async () => {
    setSavingM(true);
    try {
      await fetch(`${API_BASE}/v1/albert/mandate`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid: getPid(), mandate }) });
      await load(); setOpenMandate(false);
    } finally { setSavingM(false); }
  };
  const savePortfolio = async () => {
    setSavingP(true);
    try {
      await fetch(`${API_BASE}/v1/portfolio`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid: getPid(), usdc: usdc === '' ? null : Number(usdc),
          positions: positions.filter((p) => p.asset).map((p) => ({ asset: p.asset, size: Number(p.size) || 0, avg_entry: Number(p.avg_entry) || 0 })) }) });
      await load(); setOpenPortfolio(false);
    } finally { setSavingP(false); }
  };

  const setM = (k, v) => setMandate((m) => ({ ...(m || {}), [k]: v }));
  const s = summary || {};

  return (
    <div className="rounded-2xl border border-sky-500/20 bg-gradient-to-b from-sky-500/[0.06] to-slate-900/40 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Wallet className="h-4 w-4 text-sky-300" />
          <h3 className="text-base font-bold text-white">Portfolio Command Centre</h3>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setOpenPortfolio((v) => !v)} className="rounded-full border border-slate-700 px-2.5 py-1 text-[11px] text-slate-300 hover:bg-slate-800">Edit holdings</button>
          <button onClick={() => setOpenMandate((v) => !v)} className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${complete ? 'border border-slate-700 text-slate-300 hover:bg-slate-800' : 'bg-amber-500 text-slate-900'}`}>{complete ? 'Edit mandate' : 'Set mandate'}</button>
        </div>
      </div>

      {!complete && (
        <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5 text-[12px] text-amber-200">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Set your <b>Trading Mandate</b> (risk tolerance + protected USDC reserve) to unlock Albert&apos;s personalised BUY / HOLD / SELL / WAIT recommendations.</span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Total value" value={fmt(s.total_value)} />
        <Stat label="USDC" value={fmt(s.usdc)} />
        <Stat label="Protected reserve" value={fmt(s.protected_reserve)} sub={`${s.reserve_pct ?? 0}% of USDC`} accent="text-slate-300" />
        <Stat label="Deployable USDC" value={fmt(s.deployable_usdc)} accent="text-emerald-400" />
      </div>

      {complete && decisions && decisions.regime && (
        <div className="mt-3">
          <RegimeBanner reg={decisions.regime} buyThresh={decisions.buyThreshold} pool={decisions.regimeDeployCeiling} />
          <div className="mt-2 rounded-xl border border-violet-500/25 bg-violet-500/[0.06] p-3">
            <p className="text-[10px] uppercase tracking-wide text-violet-300">Albert&apos;s call</p>
            <p className="mt-0.5 text-sm font-semibold text-white">{decisions.albertCall}</p>
          </div>
          <div className="mt-2 overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full text-left text-[12px]">
              <thead><tr className="bg-slate-900/60 text-[10px] uppercase text-slate-500">
                <th className="py-1.5 pl-3 pr-2">Asset</th><th className="pr-2">Call</th><th className="pr-2">Score</th>
                <th className="pr-2">Conf</th><th className="pr-2">Recommendation</th><th className="pr-3"></th></tr></thead>
              <tbody>
                {decisions.decisions.map((d) => (
                  <React.Fragment key={d.symbol}>
                    <tr className="border-t border-slate-800/60 hover:bg-slate-900/40">
                      <td className="py-1.5 pl-3 pr-2 font-semibold text-slate-200">{d.symbol}</td>
                      <td className="pr-2"><div className="flex flex-col gap-0.5"><div className="flex flex-wrap items-center gap-1"><ActionPill a={d.action} big />{d.action === 'SELL' && <SellActionPill p={d.sellPlan} />}<EligibilityChip d={d} /></div>{d.action === 'SELL' && <span className="text-[9px] text-slate-500">{REASON_LABEL[d.reasonCode] || d.reasonCode}</span>}</div></td>
                      <td className="pr-2 text-[11px] text-slate-400">{d.opportunityScore}</td>
                      <td className="pr-2 text-[11px] text-slate-500">{d.confidence}%</td>
                      <td className="pr-2"><CallCell d={d} /></td>
                      <td className="pr-3 text-right"><button onClick={() => setExpanded(expanded === d.symbol ? null : d.symbol)} className="text-slate-500 hover:text-slate-200"><ChevronDown className={`h-4 w-4 transition-transform ${expanded === d.symbol ? 'rotate-180' : ''}`} /></button></td>
                    </tr>
                    {expanded === d.symbol && (
                      <tr className="border-t border-slate-800/40 bg-slate-950/40"><td colSpan={6} className="px-3 py-2">
                        {d.action === 'SELL' && d.sellPlan && (
                          <div className="mb-2 rounded-lg border border-rose-500/25 bg-rose-500/[0.06] p-2.5">
                            <p className="mb-1 flex items-center gap-1 text-[10px] uppercase text-rose-300"><Layers className="h-3 w-3" />Sell plan — {REASON_LABEL[d.reasonCode] || d.reasonCode} <span className="text-slate-500">(precedence #{precedenceRank(d.reasonCode, decisions.precedenceOrder)})</span></p>
                            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] sm:grid-cols-4">
                              <div><span className="text-slate-500">Action</span><div className="font-bold text-rose-200">{d.sellPlan.action === 'EXIT_100' ? 'EXIT 100%' : d.sellPlan.action.replace('TRIM_', 'TRIM ') + '%'}</div></div>
                              <div><span className="text-slate-500">Sell USD</span><div className="font-semibold text-slate-200">{fmtX(d.sellPlan.sellUsd)}</div></div>
                              <div><span className="text-slate-500">Sell qty</span><div className="font-semibold text-slate-200">{qty(d.sellPlan.sellQty)}</div></div>
                              <div><span className="text-slate-500">Δ</span><div className="font-semibold text-rose-300">{fmtX(d.recommendedDeltaUsd)}</div></div>
                            </div>
                            <p className="mt-1 text-[11px] text-slate-400">Position {fmtX(d.positionBefore?.valueUsd)} ({d.positionBefore?.pct}%) <ArrowRight className="inline h-3 w-3" /> {fmtX(d.positionAfter?.valueUsd)} ({d.positionAfter?.pct}%)</p>
                            {d.sellPlan.allSignals && d.sellPlan.allSignals.length > 1 && <p className="mt-1 text-[10px] text-slate-500">Also fired (lower precedence): {d.sellPlan.allSignals.filter((s) => s !== d.reasonCode).join(', ')}.</p>}
                          </div>
                        )}
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <div>
                            <p className="mb-1 text-[10px] uppercase text-slate-500">Why</p>
                            <ul className="space-y-0.5 text-[11px] text-slate-300">{(d.reasons || []).map((r, i) => <li key={i}>• {r}</li>)}</ul>
                            {!d.eligible && <p className="mt-1 text-[11px] text-amber-400">⚠ Ineligible — {INELIG_LABEL[d.ineligibilityReason] || d.ineligibilityReason} (scored {d.opportunityScore}, but never a BUY until this clears).</p>}
                            {(d.warnings || []).map((w, i) => <p key={i} className="mt-1 text-[11px] text-amber-400">⚠ {w}</p>)}
                            {d.invalidationPrice ? <p className="mt-1 text-[11px] text-rose-400">Invalidation ≈ {fmtX(d.invalidationPrice)}</p> : null}
                            {(d.riskFlags && d.riskFlags.length > 0) && <div className="mt-1 flex flex-wrap gap-1">{d.riskFlags.map((f) => <span key={f} className="rounded border border-rose-500/30 px-1 py-0.5 text-[9px] text-rose-300">{f.replace(/_/g, ' ')}</span>)}</div>}
                          </div>
                          <div>
                            <p className="mb-1 text-[10px] uppercase text-slate-500">Score breakdown <span className="text-slate-600">(separate from confidence {d.confidence}%)</span></p>
                            <div className="flex flex-wrap gap-1">{Object.entries(d.scoreComponents || {}).map(([k, v]) => <span key={k} className="rounded-full border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400">{k} {v}</span>)}</div>
                            {(d.tranches && d.tranches.length > 0) && (<div className="mt-2"><p className="mb-1 text-[10px] uppercase text-slate-500">Tranche plan</p>{d.tranches.map((t) => <div key={t.number} className="flex justify-between text-[11px] text-slate-300"><span>T{t.number} · {t.pct}% · {t.trigger.replace(/_/g, ' ').toLowerCase()}</span><span className="text-slate-400">{fmtX(t.amountUsd)}</span></div>)}</div>)}
                          </div>
                        </div>
                        <div className="mt-2 rounded-lg border border-slate-800 bg-slate-950/40 p-2.5">
                          <p className="mb-1 flex items-center gap-1 text-[10px] uppercase text-slate-500"><Info className="h-3 w-3" />What would change this?</p>
                          <FlipConditions items={d.flipConditions} />
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <button onClick={() => setExplainFor(d)} className="inline-flex items-center gap-1 rounded-full border border-violet-500/40 bg-violet-500/10 px-2.5 py-1 text-[11px] font-semibold text-violet-200 hover:bg-violet-500/20"><MessageCircle className="h-3 w-3" />Ask Albert about this call</button>
                          <button onClick={() => setHistoryFor(d.symbol)} className="inline-flex items-center gap-1 rounded-full border border-slate-700 px-2.5 py-1 text-[11px] text-slate-300 hover:bg-slate-800"><History className="h-3 w-3" />History</button>
                        </div>
                      </td></tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-1.5 text-[10px] text-slate-600">Deterministic engine {decisions.engineVersion} · advisory / paper only · Albert explains these calls, he doesn&apos;t change them.</p>
        </div>
      )}

      {(s.holdings && s.holdings.length > 0) && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-[12px]">
            <thead><tr className="text-[10px] uppercase text-slate-500"><th className="py-1 pr-3">Asset</th><th className="pr-3">Value</th><th className="pr-3">% of port</th><th className="pr-3">Unrealised</th></tr></thead>
            <tbody>
              {s.holdings.map((h) => (
                <tr key={h.asset} className="border-t border-slate-800/60">
                  <td className="py-1.5 pr-3 font-semibold text-slate-200">{h.asset}</td>
                  <td className="pr-3 text-slate-300">{fmt(h.value)}</td>
                  <td className="pr-3 text-slate-400">{h.portfolio_pct}%</td>
                  <td className={`pr-3 font-medium ${h.unrealized_pct == null ? 'text-slate-500' : h.unrealized_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{h.unrealized_pct == null ? '—' : `${h.unrealized_pct >= 0 ? '+' : ''}${h.unrealized_pct}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {openPortfolio && (
        <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-300"><Wallet className="h-3.5 w-3.5" />Your holdings &amp; USDC (manual)</div>
          <label className="mb-2 block text-[11px] text-slate-400">USDC balance
            <input type="number" value={usdc} onChange={(e) => setUsdc(e.target.value)} placeholder="e.g. 50000" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200" /></label>
          <div className="space-y-1.5">
            {positions.map((p, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <input value={p.asset} onChange={(e) => setPositions((a) => a.map((x, j) => j === i ? { ...x, asset: e.target.value.toUpperCase() } : x))} placeholder="COIN" className="w-20 rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-[12px] text-slate-200" />
                <input type="number" value={p.size} onChange={(e) => setPositions((a) => a.map((x, j) => j === i ? { ...x, size: e.target.value } : x))} placeholder="qty" className="w-24 rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-[12px] text-slate-200" />
                <input type="number" value={p.avg_entry} onChange={(e) => setPositions((a) => a.map((x, j) => j === i ? { ...x, avg_entry: e.target.value } : x))} placeholder="avg entry $" className="w-28 rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-[12px] text-slate-200" />
                <button onClick={() => setPositions((a) => a.filter((_, j) => j !== i))} className="text-slate-500 hover:text-rose-400"><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
          </div>
          <button onClick={() => setPositions((a) => [...a, { asset: '', size: '', avg_entry: '' }])} className="mt-2 flex items-center gap-1 text-[11px] text-sky-400 hover:text-sky-300"><Plus className="h-3 w-3" />Add holding</button>
          <div className="mt-3 flex justify-end"><Button onClick={savePortfolio} disabled={savingP} className="h-8 bg-sky-600 text-white hover:bg-sky-500">{savingP ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Check className="mr-1 h-3.5 w-3.5" />}Save holdings</Button></div>
        </div>
      )}

      {openMandate && mandate && (
        <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-300"><Target className="h-3.5 w-3.5" />Trading Mandate</div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="text-[11px] text-slate-400">Goal
              <input value={mandate.goal || ''} onChange={(e) => setM('goal', e.target.value)} placeholder="e.g. Long-term capital growth" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200" /></label>
            <label className="text-[11px] text-slate-400">Risk tolerance
              <select value={mandate.risk_tolerance || ''} onChange={(e) => setM('risk_tolerance', e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200">
                <option value="">Select…</option><option value="conservative">Conservative</option><option value="moderate">Moderate</option><option value="aggressive">Aggressive</option></select></label>
            <label className="text-[11px] text-slate-400">Time horizon
              <input value={mandate.time_horizon || ''} onChange={(e) => setM('time_horizon', e.target.value)} placeholder="e.g. 6–12 months" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200" /></label>
            <label className="text-[11px] text-slate-400">Max portfolio drawdown %
              <input type="number" value={mandate.max_drawdown_pct ?? ''} onChange={(e) => setM('max_drawdown_pct', e.target.value === '' ? null : Number(e.target.value))} placeholder="e.g. 20" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200" /></label>
            <label className="text-[11px] text-slate-400">Protected USDC reserve %
              <input type="number" value={mandate.reserve_pct ?? ''} onChange={(e) => setM('reserve_pct', e.target.value === '' ? null : Number(e.target.value))} placeholder="e.g. 25" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200" /></label>
            <label className="text-[11px] text-slate-400">Max trade risk %
              <input type="number" value={mandate.max_trade_risk_pct ?? ''} onChange={(e) => setM('max_trade_risk_pct', e.target.value === '' ? null : Number(e.target.value))} placeholder="e.g. 2" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200" /></label>
            <label className="text-[11px] text-slate-400 sm:col-span-2">Approved coins (comma-separated, blank = top 100)
              <input value={(mandate.approved_coins || []).join(', ')} onChange={(e) => setM('approved_coins', e.target.value.split(',').map((x) => x.trim().toUpperCase()).filter(Boolean))} placeholder="e.g. BTC, ETH, SOL" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200" /></label>
          </div>
          <label className="mt-2 flex items-center gap-2 text-[12px] text-slate-300"><input type="checkbox" checked={!!mandate.leverage_enabled} onChange={(e) => setM('leverage_enabled', e.target.checked)} className="h-4 w-4 rounded border-slate-600 bg-slate-900" />Enable leverage (off by default)</label>
          <div className="mt-3 flex justify-end"><Button onClick={saveMandate} disabled={savingM} className="h-8 bg-amber-500 text-slate-900 hover:bg-amber-400">{savingM ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Check className="mr-1 h-3.5 w-3.5" />}Save mandate</Button></div>
        </div>
      )}

      {explainFor && <ExplainModal decision={explainFor} onClose={() => setExplainFor(null)} />}
      {historyFor && <HistoryDrawer asset={historyFor} onClose={() => setHistoryFor(null)} />}
    </div>
  );
}
