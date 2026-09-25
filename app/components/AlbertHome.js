'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  Sparkles, TrendingUp, TrendingDown, Activity, AlertTriangle, CheckCircle2,
  Gauge, FlaskConical, Crosshair, MessageCircle, ArrowRight, Loader2, ShieldCheck,
  Clock, Wallet, Layers, Database, Lightbulb, Lock, PauseCircle, PlayCircle, ChevronRight,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { API_BASE } from '../lib/api';

/* ----------------------------- helpers ----------------------------- */
const num = (v) => (v === null || v === undefined || v === '' ? null : Number(v));
const money = (v) => {
  const n = num(v);
  if (n === null || Number.isNaN(n)) return '—';
  return '$' + n.toLocaleString(undefined, { maximumFractionDigits: n >= 1000 ? 0 : 2 });
};
const pct = (v) => {
  const n = num(v);
  if (n === null || Number.isNaN(n)) return null;
  return n;
};
const REGIME_META = {
  BULL: { label: 'Bullish', color: 'text-emerald-400', dot: 'bg-emerald-400' },
  BEAR: { label: 'Bearish', color: 'text-red-400', dot: 'bg-red-400' },
  RANGE: { label: 'Range-bound', color: 'text-amber-400', dot: 'bg-amber-400' },
  UNKNOWN: { label: 'Uncertain', color: 'text-slate-400', dot: 'bg-slate-500' },
};
const MODE_META = {
  OBSERVE: { label: 'Observe', hint: 'Albert monitors and explains — no paper orders are placed.', color: 'text-sky-300', ring: 'ring-sky-500/30' },
  APPROVAL_REQUIRED: { label: 'Approval Required', hint: 'Albert prepares proposals; you approve or reject before any paper trade.', color: 'text-amber-300', ring: 'ring-amber-500/30' },
  PAPER_AUTOPILOT: { label: 'Paper Autopilot', hint: 'The deterministic worker executes simulated trades within your strategy and mandate.', color: 'text-violet-300', ring: 'ring-violet-500/30' },
};

function timeAgo(iso) {
  if (!iso) return '';
  const t = Date.now() - new Date(String(iso).replace('Z', '') + 'Z').getTime();
  if (Number.isNaN(t)) return '';
  const m = Math.floor(t / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// Deep-link ("/?section=paper&proposal=..") → SPA section id.
function sectionFromDeepLink(dl) {
  if (!dl) return null;
  try {
    const q = new URLSearchParams(dl.split('?')[1] || '');
    return q.get('section');
  } catch (e) { return null; }
}

/* --------------- deterministic plain-English briefing --------------- */
// Composed strictly from the authoritative state of play — Albert explains, he
// does not invent. (LLM enrichment arrives in the Ask-Albert milestone.)
function buildBriefing(sop) {
  if (!sop) return [];
  const lines = [];
  const rm = REGIME_META[sop.market?.regime] || REGIME_META.UNKNOWN;
  const fresh = sop.market?.freshness;
  if (fresh === 'STALE' || fresh === 'MISSING') {
    lines.push(`I'm holding off on new action calls — the market read is ${fresh === 'MISSING' ? 'unavailable' : 'not fresh'} right now, so I'd rather wait for reliable data than guess.`);
  } else {
    lines.push(`The market is reading **${rm.label.toLowerCase()}** at the moment. I'm using that to frame how I weigh every other signal.`);
  }
  const p = sop.portfolio;
  if (p) {
    lines.push(`Your paper account is worth ${money(p.totalValue)} with ${money(p.deployableCapital)} deployable after your protected reserve of ${money(p.protectedReserve)}.`);
    const positions = (p.positions || []).length;
    if (positions > 0) lines.push(`You're holding ${positions} open ${positions === 1 ? 'position' : 'positions'}, which I'm monitoring against their invalidation levels.`);
  }
  const acts = (sop.attention || []).filter((a) => a.severity === 'ACTION');
  if (acts.length) lines.push(`There ${acts.length === 1 ? 'is' : 'are'} ${acts.length} ${acts.length === 1 ? 'decision' : 'decisions'} waiting on you below.`);
  else lines.push(`Nothing needs a decision from you right now — I'll surface something the moment it's genuinely actionable.`);
  return lines;
}

function boldToJsx(text) {
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => (p.startsWith('**') && p.endsWith('**'))
    ? <strong key={i} className="font-semibold text-white">{p.slice(2, -2)}</strong>
    : <span key={i}>{p}</span>);
}

/* ------------------------------ sub-cards ------------------------------ */
function StatusStrip({ sop }) {
  const rm = REGIME_META[sop.market?.regime] || REGIME_META.UNKNOWN;
  const p = sop.portfolio || {};
  const perf = sop.paper?.performance || {};
  const chg = pct(p.unrealizedPnl);
  const dq = sop.dataQuality?.status || 'HEALTHY';
  const dqColor = dq === 'HEALTHY' ? 'text-emerald-400' : dq === 'DEGRADED' ? 'text-amber-400' : 'text-red-400';
  const Item = ({ icon: Icon, label, children }) => (
    <div className="flex min-w-0 items-center gap-2.5 rounded-xl border border-slate-800 bg-slate-950/50 px-3.5 py-2.5">
      <Icon className="h-4 w-4 shrink-0 text-slate-500" />
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-wider text-slate-500">{label}</p>
        <div className="truncate text-sm font-bold text-white">{children}</div>
      </div>
    </div>
  );
  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
      <Item icon={Activity} label="Market stance">
        <span className={rm.color}><span className={`mr-1.5 inline-block h-2 w-2 rounded-full ${rm.dot} align-middle`} />{rm.label}</span>
      </Item>
      <Item icon={Wallet} label="Paper value">{money(p.totalValue)}</Item>
      <Item icon={Gauge} label="Deployable">{money(p.deployableCapital)}</Item>
      <Item icon={p && chg >= 0 ? TrendingUp : TrendingDown} label="Unrealised P&L">
        <span className={chg == null ? 'text-slate-300' : chg >= 0 ? 'text-emerald-400' : 'text-red-400'}>{p.unrealizedPnl != null ? money(p.unrealizedPnl) : '—'}</span>
      </Item>
      <Item icon={Database} label="Data status"><span className={dqColor}>{dq === 'HEALTHY' ? 'Healthy' : dq === 'DEGRADED' ? 'Degraded' : 'Limited'}</span></Item>
    </div>
  );
}

function EvidenceLink({ label = 'Evidence', deepLink, onEvidence }) {
  if (!deepLink) return null;
  return (
    <button onClick={() => onEvidence(deepLink)}
      className="inline-flex items-center gap-1 text-[11px] font-semibold text-sky-400 underline decoration-sky-500/40 underline-offset-2 hover:text-sky-300">
      <ShieldCheck className="h-3 w-3" />{label}
    </button>
  );
}

function BriefingCard({ sop, onNav, onEvidence }) {
  const lines = buildBriefing(sop);
  const ev = sop.evidenceIndex?.['market.regime'];
  return (
    <Card className="border-0 bg-gradient-to-br from-sky-500/[0.07] via-violet-500/[0.06] to-slate-900 p-6 ring-1 ring-sky-500/25">
      <div className="mb-3 flex items-center gap-3">
        <img src="/albert.png" alt="Albert" className="h-11 w-11 rounded-full object-cover ring-2 ring-sky-500/40" />
        <div>
          <h2 className="text-base font-bold text-white">Albert’s briefing</h2>
          <p className="text-[11px] text-slate-400">Your HuCentAI trading companion · {timeAgo(sop.generatedAt) || 'live'}</p>
        </div>
        <Badge variant="outline" className="ml-auto border-slate-700 text-[10px] text-slate-300">Paper only</Badge>
      </div>
      <div className="max-w-[70ch] space-y-2 text-[15px] leading-relaxed text-slate-200">
        {lines.map((l, i) => <p key={i}>{boldToJsx(l)}</p>)}
      </div>
      {(sop.changesSinceLastVisit || []).length > 0 && (
        <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
          <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400"><Clock className="h-3.5 w-3.5" />What changed since you were last here</p>
          <ul className="space-y-1 text-[13px] text-slate-300">
            {sop.changesSinceLastVisit.slice(0, 5).map((c, i) => (
              <li key={i} className="flex items-start gap-2"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-400" /><span>{c.detail || c.kind} <span className="text-slate-500">· {timeAgo(c.at)}</span></span></li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => onNav('ask')} className="gap-1.5 bg-gradient-to-r from-sky-500 to-violet-600 text-white hover:from-sky-400 hover:to-violet-500">
          <MessageCircle className="h-4 w-4" />Ask Albert
        </Button>
        <EvidenceLink deepLink={ev?.deepLink} onEvidence={onEvidence} />
      </div>
    </Card>
  );
}

function DecisionCard({ item, onNav, onEvidence }) {
  const isAction = item.severity === 'ACTION';
  const isWarn = item.severity === 'WARNING';
  const tone = isAction ? 'border-amber-500/40 bg-amber-500/[0.06]' : isWarn ? 'border-red-500/40 bg-red-500/[0.06]' : 'border-sky-500/30 bg-sky-500/[0.05]';
  const Icon = isAction ? AlertTriangle : isWarn ? AlertTriangle : Lightbulb;
  const iconColor = isAction ? 'text-amber-400' : isWarn ? 'text-red-400' : 'text-sky-400';
  const target = sectionFromDeepLink(item.deepLink) || 'paper';
  return (
    <div className={`rounded-xl border p-4 ${tone}`}>
      <div className="flex items-start gap-2.5">
        <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${iconColor}`} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-white">{item.title}</p>
          {item.expiresAt && <p className="mt-0.5 text-[11px] text-slate-400">Expires {timeAgo(item.expiresAt) || 'soon'} · re-checked freshly on approval</p>}
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={() => onNav(target)}
              className="h-7 gap-1 bg-slate-100 px-2.5 text-[12px] font-semibold text-slate-900 hover:bg-white">
              {item.kind === 'PROPOSAL_APPROVAL' ? 'Review paper trade' : item.kind === 'MANDATE_INCOMPLETE' ? 'Set up mandate' : item.kind === 'NO_ASSIGNED_STRATEGY' ? 'Build a strategy' : item.kind === 'NO_PAPER_ACCOUNT' ? 'Create paper account' : 'Open'}
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
            <EvidenceLink deepLink={item.deepLink} onEvidence={onEvidence} />
          </div>
        </div>
      </div>
    </div>
  );
}

function NeedsDecision({ sop, onNav, onEvidence }) {
  const items = (sop.attention || []).filter((a) => a.severity === 'ACTION' || a.severity === 'WARNING');
  if (!items.length) {
    return (
      <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
        <div className="flex items-center gap-2 text-sm font-semibold text-white"><CheckCircle2 className="h-4 w-4 text-emerald-400" />Nothing needs your decision</div>
        <p className="mt-1 text-[13px] text-slate-400">You're all caught up. Albert will raise something the instant it's genuinely actionable.</p>
      </Card>
    );
  }
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-bold text-white"><AlertTriangle className="h-4 w-4 text-amber-400" />Needs your decision</h3>
      <div className="space-y-2.5">
        {items.map((it) => <DecisionCard key={it.id} item={it} onNav={onNav} onEvidence={onEvidence} />)}
      </div>
    </Card>
  );
}

function Managing({ sop, onNav, onEvidence }) {
  const paper = sop.paper;
  if (!paper) {
    return (
      <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
        <h3 className="mb-1 flex items-center gap-2 text-sm font-bold text-white"><FlaskConical className="h-4 w-4 text-sky-400" />Albert is managing</h3>
        <p className="text-[13px] text-slate-400">No paper account yet. Create one and Albert can put an authorised strategy into simulated action.</p>
        <Button size="sm" onClick={() => onNav('paper')} className="mt-3 gap-1.5 bg-sky-500 hover:bg-sky-400">Create paper account<ArrowRight className="h-3.5 w-3.5" /></Button>
      </Card>
    );
  }
  const mode = MODE_META[paper.mode] || MODE_META.OBSERVE;
  const acct = paper.selectedAccount || {};
  const wh = paper.workerHealth || {};
  const positions = paper.positions || [];
  const lastAct = (paper.recentActivity || [])[0];
  const paused = acct.runtimeState && acct.runtimeState !== 'RUNNING';
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-2 text-sm font-bold text-white"><FlaskConical className="h-4 w-4 text-sky-400" />Albert is managing</h3>
        <span className={`ml-auto rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1 ${mode.ring} ${mode.color}`}>{mode.label}</span>
      </div>
      <p className="mb-3 text-[12px] text-slate-400">{mode.hint}</p>
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Account</p><p className="truncate text-sm font-bold text-white">{acct.name || '—'}</p></div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Strategy</p><p className="truncate text-sm font-bold text-white">{acct.assignedStrategy?.name || paper.assignedStrategy?.name || 'None assigned'}</p></div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Open positions</p><p className="text-sm font-bold text-white">{positions.length}</p></div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Pending</p><p className="text-sm font-bold text-white">{(paper.pendingProposals || []).length}</p></div>
      </div>
      {positions.length > 0 && (
        <div className="mt-3 overflow-hidden rounded-lg border border-slate-800">
          <table className="w-full text-[13px]">
            <thead className="bg-slate-950/60 text-[10px] uppercase tracking-wider text-slate-500"><tr><th className="px-3 py-1.5 text-left font-medium">Asset</th><th className="px-3 py-1.5 text-right font-medium">Qty</th><th className="px-3 py-1.5 text-right font-medium">Avg entry</th><th className="px-3 py-1.5 text-right font-medium">Unreal. P&L</th></tr></thead>
            <tbody>
              {positions.slice(0, 5).map((p, i) => {
                const up = pct(p.unrealizedPnl);
                return (
                  <tr key={p.paperPositionId || i} className="border-t border-slate-800/70">
                    <td className="px-3 py-1.5 font-semibold text-slate-200">{p.asset}</td>
                    <td className="px-3 py-1.5 text-right font-mono text-slate-300">{p.netQuantity}</td>
                    <td className="px-3 py-1.5 text-right font-mono text-slate-400">{money(p.averageEntryPrice)}</td>
                    <td className={`px-3 py-1.5 text-right font-mono ${up == null ? 'text-slate-500' : up >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{p.unrealizedPnl != null ? money(p.unrealizedPnl) : '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12px] text-slate-400">
        {lastAct && <span className="flex items-center gap-1"><Activity className="h-3.5 w-3.5 text-slate-500" />Last: {lastAct.note || lastAct.type} <span className="text-slate-600">· {timeAgo(lastAct.recordedAt || lastAct.effectiveAt)}</span></span>}
        {paused ? (
          <span className="flex items-center gap-1 text-amber-400"><PauseCircle className="h-3.5 w-3.5" />{acct.runtimeState === 'PAUSED_RISK_BREAKER' ? 'Paused by drawdown breaker' : 'Paused'}</span>
        ) : (
          <span className="flex items-center gap-1 text-emerald-400"><PlayCircle className="h-3.5 w-3.5" />Running</span>
        )}
        <button onClick={() => onNav('paper')} className="ml-auto inline-flex items-center gap-1 font-semibold text-sky-400 hover:text-sky-300">Open Paper Trading<ChevronRight className="h-3.5 w-3.5" /></button>
      </div>
    </Card>
  );
}

function StrategiesRow({ sop, onNav }) {
  const s = sop.strategies || {};
  const all = [...(s.needsAttention || []), ...(s.active || []), ...(s.drafts || [])];
  const seen = new Set();
  const cards = all.filter((x) => x.id && !seen.has(x.id) && seen.add(x.id)).slice(0, 4);
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="mb-3 flex items-center gap-2">
        <h3 className="flex items-center gap-2 text-sm font-bold text-white"><Crosshair className="h-4 w-4 text-violet-400" />Your strategies</h3>
        <button onClick={() => onNav('strategies')} className="ml-auto inline-flex items-center gap-1 text-[12px] font-semibold text-sky-400 hover:text-sky-300">Open Strategies<ChevronRight className="h-3.5 w-3.5" /></button>
      </div>
      {cards.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-700 bg-slate-950/40 p-4 text-center">
          <p className="text-[13px] text-slate-400">You haven’t built a strategy yet. Describe your objective and Albert will draft one with you.</p>
          <Button size="sm" onClick={() => onNav('strategies')} className="mt-3 gap-1.5 bg-violet-600 hover:bg-violet-500">Build a strategy<ArrowRight className="h-3.5 w-3.5" /></Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          {cards.map((c) => (
            <button key={c.id} onClick={() => onNav('strategies')} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-left transition-colors hover:border-violet-500/40">
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-sm font-semibold text-white">{c.name}</p>
                <Badge variant="outline" className="shrink-0 border-slate-700 text-[10px] capitalize text-slate-300">{(c.status || '').replace(/_/g, ' ') || 'draft'}</Badge>
              </div>
              <p className="mt-1 truncate text-[12px] text-slate-500">{Array.isArray(c.assets) ? c.assets.map((a) => a.symbol || a.asset || a).join(' · ') : (c.symbol || 'Multi-asset')}</p>
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}

function OppsRisks({ sop }) {
  // Keep the four states distinct (spec §4.1 F): opportunity ≠ mandate ≠ strategy ≠ recommend now.
  const rows = [
    { label: 'Opportunity exists', ok: (sop.market?.freshness === 'FRESH') && sop.market?.regime === 'BULL', note: sop.market?.regime ? `Market is ${(REGIME_META[sop.market.regime] || REGIME_META.UNKNOWN).label.toLowerCase()}.` : 'Waiting for a fresh market read.' },
    { label: 'Your mandate permits action', ok: sop.user?.mandateStatus === 'COMPLETE', note: sop.user?.mandateStatus === 'COMPLETE' ? 'Mandate is complete.' : 'Complete your mandate first.' },
    { label: 'Your strategy permits action', ok: (sop.strategies?.active || []).length > 0, note: (sop.strategies?.active || []).length > 0 ? 'An active strategy is available.' : 'No active strategy assigned yet.' },
    { label: 'Albert recommends action now', ok: (sop.attention || []).some((a) => a.severity === 'ACTION'), note: (sop.attention || []).some((a) => a.severity === 'ACTION') ? 'There is a decision waiting.' : 'No action recommended right now.' },
  ];
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-bold text-white"><Layers className="h-4 w-4 text-emerald-400" />Opportunities &amp; risks</h3>
      <div className="space-y-2">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center gap-2.5 rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">
            {r.ok ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" /> : <Lock className="h-4 w-4 shrink-0 text-slate-500" />}
            <div className="min-w-0">
              <p className="text-[13px] font-semibold text-slate-200">{r.label}</p>
              <p className="truncate text-[11px] text-slate-500">{r.note}</p>
            </div>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">These four checks are independent — an opportunity is not permission, and permission is not a recommendation. Albert only acts when your mandate, strategy and safety checks all pass.</p>
    </Card>
  );
}

/* ------------------------------ main ------------------------------ */
export default function AlbertHome({ onNav }) {
  const [sop, setSop] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error | signedout
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/v1/albert/state-of-play`, { credentials: 'include', cache: 'no-store' });
      if (r.status === 401 || r.status === 403) { setStatus('signedout'); return; }
      if (!r.ok) { setErr('Could not load your state of play.'); setStatus('error'); return; }
      const j = await r.json();
      setSop(j); setStatus('ready');
    } catch (e) { setErr('Network error loading your state of play.'); setStatus('error'); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onEvidence = useCallback((deepLink) => {
    const s = sectionFromDeepLink(deepLink);
    if (s && onNav) onNav(s);
  }, [onNav]);

  if (status === 'loading') {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-slate-400">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />Albert is reading your state of play…
      </div>
    );
  }
  if (status === 'error') {
    return (
      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <p className="flex items-center gap-2 text-sm font-semibold text-amber-300"><AlertTriangle className="h-4 w-4" />{err}</p>
        <Button size="sm" onClick={load} className="mt-3 bg-sky-500 hover:bg-sky-400">Retry</Button>
      </Card>
    );
  }
  if (status === 'signedout' || !sop) {
    return (
      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <p className="text-sm text-slate-300">Please sign in to see Albert’s home.</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2.5">
        <Sparkles className="h-5 w-5 text-amber-400" />
        <h1 className="text-lg font-bold text-white">Albert</h1>
        <span className="text-[12px] text-slate-500">Your HuCentAI trading companion</span>
      </div>

      <StatusStrip sop={sop} />

      {/* Desktop/laptop: briefing + positions on the left, decisions on the right. */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <BriefingCard sop={sop} onNav={onNav} onEvidence={onEvidence} />
          <Managing sop={sop} onNav={onNav} onEvidence={onEvidence} />
          <StrategiesRow sop={sop} onNav={onNav} />
        </div>
        <div className="space-y-4">
          <NeedsDecision sop={sop} onNav={onNav} onEvidence={onEvidence} />
          <OppsRisks sop={sop} />
        </div>
      </div>

      <p className="pt-1 text-center text-[11px] text-slate-600">Paper trading only — no real orders are placed. Albert explains the deterministic engine’s decisions; he never invents or alters trades.</p>
    </div>
  );
}
