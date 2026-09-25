'use client';
// Paper-Trading Bot — paper-only forward test of Albert's deterministic engine.
// Create an account, pick a mode (Observe / Ask me first / Autopilot), review & approve
// proposals, watch simulated fills, positions, equity and the activity ledger. No real
// money, no exchange keys — ever. Every screen carries a "Paper only" badge.
import React from 'react';
import { API_BASE, getPid } from '../lib/api';
import {
  Loader2, FlaskConical, Play, Pause, Bot, Eye, HandCoins, ShieldCheck, CheckCircle2,
  XCircle, TrendingUp, AlertTriangle, Info, ArrowRight,
} from 'lucide-react';

const usd = (v) => (v == null ? '\u2014' : '$' + Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }));
const num = (v) => (v == null ? 0 : Number(v));
const MODES = [
  { id: 'OBSERVE', label: 'Observe only', desc: 'Albert logs signals but never trades.', Icon: Eye },
  { id: 'APPROVAL_REQUIRED', label: 'Ask me first', desc: 'Albert proposes; you approve each paper trade.', Icon: HandCoins },
  { id: 'PAPER_AUTOPILOT', label: 'Run Paper Autopilot', desc: 'Albert trades automatically in the background — paper only.', Icon: Bot },
];

function PaperBadge() {
  return <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300"><FlaskConical className="h-3 w-3" />Paper only</span>;
}

// M5.1 — one metric row: current value vs its limit, with a labelled bar (never colour alone).
function LimitBar({ label, valuePct, limitPct }) {
  const v = valuePct == null ? null : Number(valuePct);
  const lim = limitPct == null ? null : Number(limitPct);
  const ratio = (v != null && lim) ? Math.min(1, v / lim) : 0;
  const near = (v != null && lim) ? (v / lim >= 0.9) : false;
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
      <div className="flex items-baseline justify-between text-[11px]">
        <span className="text-slate-400">{label}</span>
        <span className="font-mono font-semibold text-slate-200">{v == null ? '—' : v + '%'}<span className="text-slate-500"> / {lim == null ? '—' : lim + '%'}</span>{near ? <span className="ml-1 font-bold text-amber-300">near limit</span> : null}</span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full ${near ? 'bg-amber-400' : 'bg-sky-400'}`} style={{ width: (ratio * 100).toFixed(0) + '%' }} />
      </div>
    </div>
  );
}

export default function PaperTradingBot() {
  const [accounts, setAccounts] = React.useState(null);
  const [acctId, setAcctId] = React.useState(null);
  const [dash, setDash] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState(null);              // approval outcome banner
  const [pendingApprove, setPendingApprove] = React.useState({});  // per-proposal in-flight guard
  const keysRef = React.useRef({});                        // one idempotency key per approval action
  const pid = typeof window !== 'undefined' ? getPid() : '';

  const keyFor = (proposalId) => {
    if (!keysRef.current[proposalId]) {
      const gen = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID() : ('idem_' + Date.now() + '_' + Math.random().toString(36).slice(2));
      keysRef.current[proposalId] = gen;
    }
    return keysRef.current[proposalId];
  };

  const loadAccounts = React.useCallback(async () => {
    if (!pid) { setAccounts([]); return; }
    try {
      const r = await fetch(`${API_BASE}/v1/albert/paper/accounts?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' });
      const j = await r.json();
      setAccounts(j.accounts || []);
      if (!acctId && j.accounts && j.accounts.length) setAcctId(j.accounts[0].paperAccountId);
    } catch (e) { setAccounts([]); }
  }, [pid, acctId]);

  const loadDash = React.useCallback(async () => {
    if (!acctId || !pid) return;
    try {
      const r = await fetch(`${API_BASE}/v1/albert/paper/accounts/${acctId}/dashboard?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' });
      const j = await r.json();
      setDash(j && j.status === 'ready' ? j : null);
    } catch (e) { setDash(null); }
  }, [acctId, pid]);

  React.useEffect(() => { loadAccounts(); }, [loadAccounts]);
  React.useEffect(() => { loadDash(); }, [loadDash]);

  const createAccount = async (mode) => {
    setBusy(true);
    try {
      const r = await fetch(`${API_BASE}/v1/albert/paper/accounts`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid, name: 'Multi-Asset Forward Test', startingCash: '100000', mode }),
      });
      const j = await r.json();
      if (j.paperAccountId) { setAcctId(j.paperAccountId); await loadAccounts(); }
    } catch (e) { /* noop */ }
    setBusy(false);
  };

  const act = async (url, body) => {
    setBusy(true);
    try { await fetch(url, { method: body === undefined ? 'POST' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pid, ...(body || {}) }) }); } catch (e) { /* noop */ }
    await loadDash(); await loadAccounts(); setBusy(false);
  };
  const setMode = async (mode) => {
    setBusy(true);
    try { await fetch(`${API_BASE}/v1/albert/paper/accounts/${acctId}/mode`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pid, mode }) }); } catch (e) { /* noop */ }
    await loadDash(); setBusy(false);
  };

  // Approval sends ONLY the contract fields — never quantity/price/invalidation/targets.
  // One idempotency key per approval action, reused on retry; double-taps are blocked.
  const approveProposal = async (p) => {
    if (pendingApprove[p.proposalId]) return;               // double-tap protection
    setPendingApprove((s) => ({ ...s, [p.proposalId]: true }));
    setMsg(null);
    const key = keyFor(p.proposalId);
    let keepKey = true;                                     // keep key so a retry reuses it
    try {
      const r = await fetch(`${API_BASE}/v1/albert/paper/proposals/${p.proposalId}/approve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expectedProposalVersion: p.version ?? 0,
          decisionSnapshotId: p.decisionSnapshotId,
          idempotencyKey: key,
        }),
      });
      if (r.status === 503) {
        setMsg({ t: 'info', m: 'Paper execution is temporarily disabled while final acceptance checks are completed. No real money is affected.' });
      } else if (r.status === 401) {
        setMsg({ t: 'err', m: 'Your session expired — please sign in again to approve.' });
      } else if (r.status === 404) {
        setMsg({ t: 'err', m: 'This proposal is no longer available.' }); keepKey = false;
      } else if (r.status === 409) {
        setMsg({ t: 'warn', m: 'This proposal expired or changed — Albert will surface a fresh one.' }); keepKey = false;
      } else if (r.status === 422) {
        setMsg({ t: 'err', m: 'The approval request was incomplete — please try again.' });
      } else if (r.ok) {
        const j = await r.json().catch(() => ({}));
        if (j.proposalStatus === 'REJECTED_ON_REVALIDATION') {
          setMsg({ t: 'warn', m: 'The decision changed on a fresh check — paper trade not placed.' }); keepKey = false;
        } else {
          setMsg({ t: 'ok', m: 'Paper trade approved and simulated. No real money was involved.' }); keepKey = false;
        }
      } else {
        setMsg({ t: 'err', m: 'Something went wrong — please retry.' });
      }
    } catch (e) {
      setMsg({ t: 'err', m: 'Network error — you can safely retry; it won’t double-fill.' });
    }
    if (!keepKey) delete keysRef.current[p.proposalId];
    await loadDash(); await loadAccounts();
    setPendingApprove((s) => { const n = { ...s }; delete n[p.proposalId]; return n; });
  };

  const cancelProposal = async (p) => {
    if (pendingApprove[p.proposalId]) return;
    setPendingApprove((s) => ({ ...s, [p.proposalId]: true }));
    try {
      await fetch(`${API_BASE}/v1/albert/paper/proposals/${p.proposalId}/cancel`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}),
      });
    } catch (e) { /* noop */ }
    delete keysRef.current[p.proposalId];
    await loadDash(); await loadAccounts();
    setPendingApprove((s) => { const n = { ...s }; delete n[p.proposalId]; return n; });
  };

  if (!pid) {
    return <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-6 text-[13px] text-slate-400">Sign in to run a paper-trading forward test.</div>;
  }
  if (accounts === null) {
    return <div className="flex items-center gap-2 text-[13px] text-slate-400"><Loader2 className="h-4 w-4 animate-spin" />Loading paper accounts…</div>;
  }

  // Empty state — no account yet.
  if (!accounts.length) {
    return (
      <div className="space-y-4">
        <div><h2 className="flex items-center gap-2 text-xl font-bold text-white"><FlaskConical className="h-5 w-5 text-amber-300" />Paper Trading Bot</h2>
          <p className="mt-0.5 text-[12px] text-slate-400">Forward-test Albert’s engine with virtual money — no exchange keys, no real orders.</p></div>
        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-5">
          <PaperBadge />
          <p className="mt-3 text-[13px] text-slate-300">Start a paper account with $100,000 virtual cash and choose how hands-on you want to be:</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {MODES.map((m) => (
              <button key={m.id} disabled={busy} onClick={() => createAccount(m.id)}
                className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-left hover:border-sky-500/40 disabled:opacity-60">
                <m.Icon className="h-5 w-5 text-sky-300" />
                <p className="mt-1.5 text-[13px] font-bold text-white">{m.label}</p>
                <p className="text-[11px] text-slate-400">{m.desc}</p>
              </button>
            ))}
          </div>
          <p className="mt-3 flex items-center gap-1.5 text-[11px] text-slate-500"><ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />This never connects to an exchange or places real trades.</p>
        </div>
      </div>
    );
  }

  const eq = dash?.equity || {};
  const acct = dash?.account || {};
  const positions = dash?.positions || [];
  const proposals = dash?.pendingProposals || [];
  const activity = dash?.recentActivity || [];
  const integ = dash?.integrity || {};
  const perf = dash?.performance || {};
  const ap = dash?.autopilot || {};
  const alloc = dash?.allocation || null;
  const rankSnap = dash?.rankingSnapshot || null;
  const rotations = dash?.rotations || [];
  const fmtTs = (t) => { try { return t ? new Date(t).toLocaleTimeString() : '—'; } catch (e) { return '—'; } };

  return (
    <div className="space-y-4">
      {/* Header + status */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="flex items-center gap-2 text-xl font-bold text-white"><FlaskConical className="h-5 w-5 text-amber-300" />Paper Trading Bot <PaperBadge /></h2>
          <p className="mt-0.5 text-[12px] text-slate-400">{acct.name} · {acct.baseCurrency} · started {usd(acct.startingCash)}</p></div>
        <div className="flex items-center gap-2">
          {acct.runtimeState === 'RUNNING'
            ? <button disabled={busy} onClick={() => act(`${API_BASE}/v1/albert/paper/accounts/${acctId}/pause`)} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-[12px] font-semibold text-slate-300 hover:text-white"><Pause className="h-3.5 w-3.5" />Pause</button>
            : <button disabled={busy} onClick={() => act(`${API_BASE}/v1/albert/paper/accounts/${acctId}/resume`)} className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-[12px] font-semibold text-emerald-300"><Play className="h-3.5 w-3.5" />Resume</button>}
        </div>
      </div>

      {/* Mode selector */}
      <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
        <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">Mode</p>
        <div className="grid gap-2 sm:grid-cols-3">
          {MODES.map((m) => {
            const on = acct.mode === m.id;
            return (
              <button key={m.id} disabled={busy} onClick={() => setMode(m.id)}
                className={`rounded-xl border p-3 text-left ${on ? 'border-sky-500/50 bg-sky-500/10' : 'border-slate-800 bg-slate-900/60 hover:border-slate-600'}`}>
                <m.Icon className={`h-4 w-4 ${on ? 'text-sky-300' : 'text-slate-400'}`} />
                <p className={`mt-1 text-[12px] font-bold ${on ? 'text-sky-200' : 'text-slate-200'}`}>{m.label}</p>
                <p className="text-[10.5px] text-slate-500">{m.desc}</p>
              </button>
            );
          })}
        </div>
        {acct.runtimeState && acct.runtimeState !== 'RUNNING' && (
          <p className="mt-2 flex items-center gap-1.5 text-[11px] font-semibold text-amber-300"><AlertTriangle className="h-3.5 w-3.5" />{acct.runtimeState.replace(/_/g, ' ')}</p>
        )}
        {integ.marketData === 'STALE' && <p className="mt-2 flex items-center gap-1.5 text-[11px] text-amber-300"><AlertTriangle className="h-3.5 w-3.5" />Market marks are stale — new paper entries are paused until data refreshes.</p>}
        <p className="mt-2 flex items-center gap-1.5 text-[10.5px] text-slate-500"><ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />Paper only — no real money, no exchange. {ap.multiAssetEnabled ? 'BTC + approved altcoins' : 'BTC spot'}, virtual USDC, long-only{ap.tradingProfile ? ` · ${ap.tradingProfile}` : ''}.</p>
      </div>

      {/* Background Autopilot status */}
      {acct.mode === 'PAPER_AUTOPILOT' && (
        <div className="rounded-2xl border border-violet-500/30 bg-violet-500/[0.06] p-4">
          <div className="mb-2 flex items-center justify-between">
            <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-violet-300"><Bot className="h-3.5 w-3.5" />Paper Autopilot {ap.autopilotEnabled && acct.runtimeState === 'RUNNING' ? 'running' : (acct.runtimeState !== 'RUNNING' ? 'paused' : 'unavailable')}</p>
            <div className="flex items-center gap-1.5">
              {ap.multiAssetEnabled && ap.tradingProfile && <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] font-bold text-violet-200">{ap.tradingProfile}</span>}
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${ap.workerState === 'running' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300'}`}>worker: {ap.workerState || 'unknown'}</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-slate-400 sm:grid-cols-3">
            {[['Last background check', fmtTs(ap.lastCheckAt)], ['Last decision processed', ap.lastDecisionProcessed ? String(ap.lastDecisionProcessed).slice(0, 10) + '…' : '—'], ['Last simulated trade', fmtTs(ap.lastTradeAt)], ['Next evaluation', fmtTs(ap.nextEvalAt)], ['Worker last run', fmtTs(ap.workerLastRunAt)]].map(([k, v], i) => (
              <div key={i}><span className="block text-[10px] uppercase tracking-wide text-slate-500">{k}</span><span className="font-semibold text-slate-200">{v}</span></div>
            ))}
          </div>
          <p className="mt-2 text-[10.5px] text-slate-500">Runs continuously on the server — you can close the app. {acct.runtimeState !== 'RUNNING' ? 'Paused: no new entries; protective exits still run.' : 'Pause any time to stop new entries.'}</p>
        </div>
      )}

      {/* Account value summary */}
      <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
        <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">Account value <span className="ml-1 text-slate-600">· marks {eq.markStatus}</span></p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 text-[12px]">
          {[['Equity', eq.value], ['Cash', eq.cash], ['Realized P&L', eq.realizedPnl], ['Unrealized P&L', eq.unrealizedPnl], ['Fees', eq.fees], ['Drawdown', (eq.drawdownPct != null ? eq.drawdownPct + '%' : '—')]].map(([k, v], i) => (
            <div key={i} className="rounded-lg border border-slate-800 bg-slate-950/60 p-2"><p className="text-slate-500">{k}</p><p className="font-mono font-semibold text-slate-200">{k.includes('%') || k === 'Drawdown' ? v : (k.includes('P&L') || k === 'Fees' || k === 'Equity' || k === 'Cash') ? usd(v) : v}</p></div>
          ))}
        </div>
      </div>

      {/* M5.1 — Portfolio allocation panel (value vs limit) */}
      {alloc && (
        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Portfolio allocation</p>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] font-bold text-violet-200">{alloc.profile}</span>
              <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-slate-300">regime {alloc.regime} · ceiling {alloc.regimeDeployCeilingPct}%</span>
            </div>
          </div>
          {!alloc.available && <p className="mb-2 flex items-center gap-1.5 text-[11px] text-amber-300"><AlertTriangle className="h-3.5 w-3.5" />Live valuation unavailable (a held asset lacks a fresh mark) — limits shown, current values paused.</p>}
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <LimitBar label="Deployed" valuePct={alloc.deployed?.pct} limitPct={alloc.deployed?.limitPct} />
            <LimitBar label="BTC exposure" valuePct={alloc.btc?.pct} limitPct={alloc.btc?.limitPct} />
            <LimitBar label="Altcoin exposure" valuePct={alloc.altcoins?.pct} limitPct={alloc.altcoins?.limitPct} />
            <LimitBar label="Combined open risk" valuePct={alloc.openRisk?.pct} limitPct={alloc.openRisk?.limitPct} />
            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
              <div className="flex items-baseline justify-between text-[11px]"><span className="text-slate-400">Open positions</span><span className="font-mono font-semibold text-slate-200">{alloc.positions?.count} / {alloc.positions?.limit}</span></div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-800"><div className="h-full bg-sky-400" style={{ width: ((Math.min(1, (alloc.positions?.count || 0) / (alloc.positions?.limit || 8))) * 100).toFixed(0) + '%' }} /></div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2"><p className="text-[11px] text-slate-400">Protected USDC</p><p className="font-mono text-[12px] font-semibold text-emerald-300">{usd(alloc.protectedUsdc)}</p></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2"><p className="text-[11px] text-slate-400">Free USDC</p><p className="font-mono text-[12px] font-semibold text-slate-200">{usd(alloc.freeUsdc)}</p></div>
            </div>
          </div>
          {rankSnap && (
            <p className="mt-2 flex flex-wrap items-center gap-1.5 text-[10.5px] text-slate-500">
              <Info className="h-3.5 w-3.5" />
              {rankSnap.available
                ? <>Ranks: {rankSnap.source || 'discovery'} · snapshot {String(rankSnap.snapshotId || '').slice(0, 8)}… · {rankSnap.fresh ? 'fresh' : 'stale'} {rankSnap.observedAt ? '· ' + fmtTs(rankSnap.observedAt) : ''}</>
                : <span className="text-amber-300">Live market-cap ranking unavailable — new altcoin sizing uses the conservative speculative cap.</span>}
            </p>
          )}
        </div>
      )}

      {/* M5.1 — Rotation activity */}
      {rotations.length > 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">Rotation activity</p>
          <div className="space-y-2">
            {rotations.map((r) => (
              <div key={r._id || (r.reducedAsset + r.at)} className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-[12px]">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-bold text-white">{r.reducedAsset}</span>
                  <ArrowRight className="h-3.5 w-3.5 text-slate-500" />
                  <span className="font-bold text-white">{r.targetAsset}</span>
                  <span className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-bold ${r.status === 'COMPLETED' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300'}`}>{r.status === 'COMPLETED' ? 'completed' : 'reduced — awaiting buy'}</span>
                </div>
                <p className="mt-1 leading-relaxed text-slate-300">{r.headline}</p>
                <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[10.5px] text-slate-500">
                  <span>scores {r.reducedScore} → {r.targetScore}</span>
                  <span>regime {r.regime}</span>
                  {r.allocationMovedUsd != null && <span>moved {usd(r.allocationMovedUsd)}</span>}
                  {r.newPositionBoundBy && <span>bound by {String(r.newPositionBoundBy).replace(/_/g, ' ').toLowerCase()}</span>}
                  <span>ranks {String(r.rankingSnapshotId || '—').slice(0, 8)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}


      {/* Approval outcome banner */}
      {msg && (
        <div className={`rounded-xl border p-3 text-[12px] font-medium ${
          msg.t === 'ok' ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
          : msg.t === 'warn' ? 'border-amber-500/40 bg-amber-500/10 text-amber-200'
          : msg.t === 'info' ? 'border-sky-500/40 bg-sky-500/10 text-sky-200'
          : 'border-rose-500/40 bg-rose-500/10 text-rose-200'}`}>
          <span className="inline-flex items-center gap-1.5"><Info className="h-3.5 w-3.5" />{msg.m}</span>
        </div>
      )}

      {/* Pending proposal */}
      {proposals.map((p) => (
        <div key={p.proposalId} className="rounded-2xl border border-sky-500/30 bg-sky-500/[0.06] p-4">
          <div className="mb-1 flex items-center justify-between"><p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-sky-300"><HandCoins className="h-3.5 w-3.5" />Paper trade proposal</p><PaperBadge /></div>
          <p className="text-[15px] font-bold text-white">{p.side} {p.asset} · {usd(p.notionalValue)}</p>
          <p className="mt-0.5 text-[12px] text-slate-400">Ref {usd(p.referencePrice)} · est. fees {usd(p.estimatedFees)}{p.invalidationPrice ? ` · invalidation ${usd(p.invalidationPrice)}` : ''}</p>
          {p.reason && <p className="mt-2 text-[12px] leading-relaxed text-slate-300">{p.reason}</p>}
          <div className="mt-3 flex gap-2">
            <button disabled={!!pendingApprove[p.proposalId]} onClick={() => approveProposal(p)} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/20 px-3.5 py-1.5 text-[12px] font-semibold text-emerald-200 hover:bg-emerald-500/30 disabled:opacity-50">{pendingApprove[p.proposalId] ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}Approve paper trade</button>
            <button disabled={!!pendingApprove[p.proposalId]} onClick={() => cancelProposal(p)} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-[12px] font-semibold text-slate-300 hover:text-white disabled:opacity-50"><XCircle className="h-3.5 w-3.5" />Skip</button>
          </div>
        </div>
      ))}

      {/* Positions */}
      <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
        <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">Open positions</p>
        {positions.length ? (
          <div className="space-y-1.5">
            {positions.map((p) => (
              <div key={p.paperPositionId} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-[12px]">
                <span className="max-w-[45%] truncate font-bold text-white">{p.asset}</span>
                {p.tier && <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide text-slate-300">{p.tier}{p.marketCapRank ? ` · #${p.marketCapRank}` : ''}{p.rankAvailable === false ? ' · rank n/a' : ''}</span>}
                <span className="text-slate-400">{Number(p.netQuantity).toLocaleString(undefined, { maximumFractionDigits: 8 })} @ {usd(p.averageEntryPrice)}</span>
                <span className="text-slate-500">now {usd(p.currentPrice)}</span>
                <span className={num(p.unrealizedPnl) >= 0 ? 'text-emerald-400' : 'text-rose-400'}>uPnL {usd(p.unrealizedPnl)}</span>
                <button disabled={busy} onClick={() => act(`${API_BASE}/v1/albert/paper/positions/${p.paperPositionId}/close`)} className="ml-auto rounded-md border border-slate-700 px-2 py-0.5 text-[11px] font-semibold text-slate-300 hover:text-white">Close</button>
              </div>
            ))}
          </div>
        ) : <p className="text-[12px] text-slate-500">No open paper positions.</p>}
      </div>

      {/* Activity */}
      <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
        <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">Activity · {perf.closedTrades || 0} closed{perf.winRatePct != null ? ` · ${perf.winRatePct}% win` : ''}</p>
        <div className="space-y-1">
          {activity.map((a, i) => (
            <div key={i} className="flex items-center gap-2 text-[11px]">
              <span className="w-40 shrink-0 font-semibold text-slate-300">{(a.eventType || '').replace(/_/g, ' ')}</span>
              <span className="flex-1 text-slate-500">{a.note}</span>
              {a.amount != null && <span className="font-mono text-slate-400">{usd(a.amount)}</span>}
            </div>
          ))}
          {!activity.length && <p className="text-[12px] text-slate-500">No activity yet.</p>}
        </div>
      </div>

      {/* Assumptions */}
      {dash?.assumptions && (
        <p className="flex items-start gap-1 text-[10px] leading-relaxed text-slate-600">
          <Info className="mt-0.5 h-3 w-3 shrink-0" />
          Conservative execution model {dash.assumptions.executionProfileId}: {dash.assumptions.feeBps}bps fee, {dash.assumptions.spreadBps}bps spread, {dash.assumptions.slippageBps}bps slippage. Paper trading — never conflated with backtests or your real portfolio, and it can never place a live order.
        </p>
      )}
    </div>
  );
}
