'use client';

import React from 'react';
import {
  Crosshair, Target, ShieldAlert, Clock, Activity, Sparkles, RefreshCw, X, Check,
  Loader2, TrendingUp, TrendingDown, History, Trophy, Bell, ArrowRight, Plus, Play,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { API_BASE } from '../lib/api';
import { fmtUsd } from '../lib/format';
import { SymbolContext } from '../lib/context';
import { SectionHead } from './shared';

const pnlColor = (v) => (v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300');
const biasBadge = (bias) => bias === 'bullish'
  ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
  : bias === 'bearish' ? 'border-red-500/40 bg-red-500/10 text-red-300'
  : 'border-slate-600 bg-slate-800/60 text-slate-300';

const kindIcon = (kind) => kind === 'price' ? Target : kind === 'time' ? Clock : Activity;
const kindLabel = (r) => {
  if (r.kind === 'price') return `If price goes ${r.op} ${fmtUsd(r.level)}`;
  if (r.kind === 'time') return r.by_days ? `After ~${r.by_days} days` : 'At the deadline';
  if (r.kind === 'signal') return r.metric === 'regime'
    ? `If regime shifts to “${r.value}”`
    : `If conviction goes ${r.op} ${r.value}`;
  return 'Rule';
};
const thenLabel = { take_profit: 'Take profit', add: 'Add', exit: 'Exit', reassess: 'Reassess', note: 'Note' };

function RuleRow({ r }) {
  const Icon = kindIcon(r.kind);
  const fired = r.status === 'fired';
  return (
    <div className={`flex items-start gap-2.5 rounded-lg border p-2.5 ${fired ? 'border-amber-500/40 bg-amber-500/5' : 'border-slate-800 bg-slate-900/40'}`}>
      <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${fired ? 'bg-amber-500/20 text-amber-300' : 'bg-slate-800 text-slate-400'}`}>
        <Icon className="h-3.5 w-3.5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold text-slate-100">
          {kindLabel(r)} <ArrowRight className="mx-0.5 inline h-3 w-3 text-slate-500" /> <span className="text-sky-300">{thenLabel[r.then] || r.then}</span>
        </p>
        <p className="text-[12px] leading-snug text-slate-400">{r.action_note}</p>
      </div>
      <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${fired ? 'bg-amber-500/20 text-amber-200' : 'bg-slate-800 text-slate-500'}`}>
        {fired ? 'FIRED' : 'WATCHING'}
      </span>
    </div>
  );
}

function TargetRow({ t, position }) {
  return (
    <div className={`flex items-center gap-2 rounded-lg border px-2.5 py-2 ${t.hit ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-slate-800 bg-slate-900/40'}`}>
      <TrendingUp className={`h-3.5 w-3.5 ${t.hit ? 'text-emerald-400' : 'text-slate-500'}`} />
      <span className="text-[13px] font-semibold text-slate-100">{t.label}</span>
      <span className="text-[13px] font-bold text-slate-200">{fmtUsd(t.price)}</span>
      <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-semibold text-slate-400">{t.pct_of_position}% off</span>
      <span className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-bold ${t.hit ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-800 text-slate-500'}`}>{t.hit ? 'HIT' : 'PENDING'}</span>
    </div>
  );
}

function EventTimeline({ events }) {
  const evs = (events || []).slice().reverse();
  if (!evs.length) return null;
  return (
    <div className="space-y-2">
      {evs.map((e, i) => (
        <div key={i} className="flex gap-2.5">
          <div className="flex flex-col items-center">
            <span className="mt-1 h-2 w-2 rounded-full bg-sky-400" />
            {i < evs.length - 1 && <span className="w-px flex-1 bg-slate-700" />}
          </div>
          <div className="pb-2">
            <p className="text-[12px] leading-snug text-slate-200">{e.message}</p>
            <p className="text-[10px] text-slate-500">
              {(() => { try { return new Date(e.ts + (/[zZ]$/.test(e.ts) ? '' : 'Z')).toLocaleString(); } catch { return e.ts; } })()}
              {e.price ? ` · ${fmtUsd(e.price)}` : ''}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function PerfHeadline({ perf, position }) {
  const p = perf || {};
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
        <p className="text-[10px] uppercase tracking-wide text-slate-500">Total P&amp;L</p>
        <p className={`text-xl font-black leading-tight ${pnlColor(p.total_pnl_pct)}`}>{p.total_pnl_pct > 0 ? '+' : ''}{p.total_pnl_pct}%</p>
        <p className={`text-[11px] font-semibold ${pnlColor(p.total_pnl_usd)}`}>{p.total_pnl_usd > 0 ? '+' : ''}{fmtUsd(p.total_pnl_usd)}</p>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
        <p className="text-[10px] uppercase tracking-wide text-slate-500">Entry → Now</p>
        <p className="text-sm font-bold text-slate-100">{fmtUsd(p.entry_price)}</p>
        <p className="text-[11px] text-slate-400">{fmtUsd(p.current_price)}</p>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
        <p className="text-[10px] uppercase tracking-wide text-slate-500">Position left</p>
        <p className="text-sm font-bold text-slate-100">{p.remaining_pct}%</p>
        <p className="text-[11px] text-slate-400 capitalize">{position}</p>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
        <p className="text-[10px] uppercase tracking-wide text-slate-500">Timeline</p>
        <p className="text-sm font-bold text-slate-100">{p.days_active}d in</p>
        <p className="text-[11px] text-slate-400">{p.days_left != null ? `${p.days_left}d left` : '—'}</p>
      </div>
    </div>
  );
}

export function DraftModal({ draft, symbol, onClose, onActivated, onRegenerate, regenerating }) {
  const [activating, setActivating] = React.useState(false);
  const activate = async () => {
    setActivating(true);
    try {
      const r = await fetch(`${API_BASE}/v1/albert/strategy`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft }),
      });
      const j = await r.json();
      if (j && j.status === 'ready') { onActivated(j.strategy); }
    } catch (e) { /* noop */ } finally { setActivating(false); }
  };
  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="relative max-h-[88vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900 p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute right-3 top-3 rounded-full bg-black/40 p-1.5 text-slate-300 hover:text-white"><X className="h-4 w-4" /></button>
        <div className="mb-1 flex items-center gap-2">
          <img src="/albert.png" alt="Albert" className="h-8 w-8 rounded-full object-cover ring-1 ring-sky-500/40" />
          <span className="text-[11px] font-bold uppercase tracking-wider text-sky-300">Albert&apos;s draft strategy</span>
        </div>
        <h2 className="text-lg font-black text-white">{draft.title}</h2>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <span className={`rounded-full border px-2 py-0.5 text-[11px] font-bold capitalize ${biasBadge(draft.bias)}`}>{draft.bias}</span>
          <span className="rounded-full border border-slate-600 bg-slate-800/60 px-2 py-0.5 text-[11px] font-semibold capitalize text-slate-300">{draft.position}</span>
          <span className="rounded-full border border-slate-600 bg-slate-800/60 px-2 py-0.5 text-[11px] font-semibold text-slate-300">{draft.horizon_days}-day horizon</span>
        </div>
        <p className="mt-3 text-[13px] leading-relaxed text-slate-300">{draft.thesis}</p>

        <p className="mt-4 mb-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-500">Profit targets</p>
        <div className="space-y-1.5">{(draft.targets || []).map((t, i) => <TargetRow key={i} t={t} position={draft.position} />)}</div>
        {draft.stop && (
          <div className="mt-1.5 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/5 px-2.5 py-2">
            <ShieldAlert className="h-3.5 w-3.5 text-red-400" />
            <span className="text-[13px] font-semibold text-slate-100">Stop</span>
            <span className="text-[13px] font-bold text-red-300">{fmtUsd(draft.stop.price)}</span>
          </div>
        )}

        <p className="mt-4 mb-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-500">If-this-then-that rules</p>
        <div className="space-y-1.5">{(draft.rules || []).map((r, i) => <RuleRow key={i} r={r} />)}</div>

        <div className="mt-5 flex gap-2">
          <Button onClick={activate} disabled={activating} className="flex-1 gap-1.5 bg-gradient-to-r from-sky-500 to-violet-500 hover:opacity-90">
            {activating ? <><Loader2 className="h-4 w-4 animate-spin" />Activating…</> : <><Play className="h-4 w-4" />Activate &amp; track</>}
          </Button>
          <Button onClick={onRegenerate} disabled={regenerating} variant="outline" className="gap-1.5 border-slate-700">
            {regenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}Redraft
          </Button>
        </div>
        <p className="mt-3 text-center text-[10px] leading-relaxed text-slate-500">Paper strategy for tracking &amp; nudges only — Albert never places real orders. Educational, not financial advice.</p>
      </div>
    </div>
  );
}

function HistoryCard({ s }) {
  const [open, setOpen] = React.useState(false);
  const win = (s.final_pnl_usd ?? 0) >= 0;
  return (
    <Card className="border-0 bg-slate-900/60 p-4 ring-1 ring-slate-800">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center gap-3 text-left">
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${win ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'}`}>
          {win ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-bold text-slate-100">{s.title}</p>
          <p className="text-[11px] text-slate-500 capitalize">{s.position} · {s.perf?.days_active}d · closed {s.close_reason?.replace('_', ' ')}</p>
        </div>
        <div className="text-right">
          <p className={`text-lg font-black leading-tight ${pnlColor(s.final_pnl_pct)}`}>{s.final_pnl_pct > 0 ? '+' : ''}{s.final_pnl_pct}%</p>
          <p className={`text-[11px] font-semibold ${pnlColor(s.final_pnl_usd)}`}>{s.final_pnl_usd > 0 ? '+' : ''}{fmtUsd(s.final_pnl_usd)}</p>
        </div>
      </button>
      {open && (
        <div className="mt-3 space-y-3 border-t border-slate-800 pt-3">
          <p className="text-[13px] leading-relaxed text-slate-300">{s.thesis}</p>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-slate-500">Plan</p>
              <div className="space-y-1.5">{(s.targets || []).map((t, i) => <TargetRow key={i} t={t} position={s.position} />)}</div>
            </div>
            <div>
              <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-slate-500">What happened</p>
              <EventTimeline events={s.events} />
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

export default function StrategiesSection() {
  const symbol = React.useContext(SymbolContext);
  const [data, setData] = React.useState(null);   // {active, history, stats}
  const [loading, setLoading] = React.useState(true);
  const [goal, setGoal] = React.useState('');
  const [building, setBuilding] = React.useState(false);
  const [draft, setDraft] = React.useState(null);
  const [closing, setClosing] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/v1/albert/strategies?symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store' });
      const j = await r.json();
      setData(j);
    } catch (e) { /* noop */ } finally { setLoading(false); }
  }, [symbol]);

  React.useEffect(() => { setLoading(true); load(); }, [load]);
  React.useEffect(() => {
    const id = setInterval(load, 30000); // keep P&L / nudges fresh
    return () => clearInterval(id);
  }, [load]);

  const build = async () => {
    setBuilding(true);
    try {
      const r = await fetch(`${API_BASE}/v1/albert/strategy/build`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, goal }),
      });
      const j = await r.json();
      if (j && j.status === 'ready') setDraft(j.draft);
    } catch (e) { /* noop */ } finally { setBuilding(false); }
  };

  const closeActive = async () => {
    const active = data?.active;
    if (!active) return;
    setClosing(true);
    try {
      await fetch(`${API_BASE}/v1/albert/strategy/${active.id}/close`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'manual' }),
      });
      await load();
    } catch (e) { /* noop */ } finally { setClosing(false); }
  };

  const active = data?.active;
  const history = data?.history || [];
  const stats = data?.stats || {};
  const coinName = active?.coin_name || symbol;

  return (
    <div className="space-y-4">
      <SectionHead icon={Crosshair} title="Trading Strategies"
        blurb={`Strategies Albert builds and babysits for ${coinName}. Each has an entry, profit targets, a stop and if-this-then-that rules on price, time and signals. Albert nudges you when it's time to act, paper-tracks the P&L, and keeps a history of how past plays performed.`} />

      {loading && !data ? (
        <Card className="border-0 bg-slate-900 p-8 text-center ring-1 ring-slate-800"><Loader2 className="mx-auto h-6 w-6 animate-spin text-slate-500" /></Card>
      ) : active ? (
        <Card className="border-0 bg-gradient-to-br from-sky-500/[0.07] via-violet-500/[0.05] to-slate-900 p-5 ring-1 ring-sky-500/25">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <img src="/albert.png" alt="Albert" className="h-10 w-10 rounded-full object-cover ring-2 ring-sky-500/40" />
            <div className="min-w-0">
              <h3 className="truncate text-lg font-black text-white">{active.title}</h3>
              <p className="text-[11px] text-slate-400">Active {coinName} strategy · Albert is tracking it</p>
            </div>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <span className={`rounded-full border px-2 py-0.5 text-[11px] font-bold capitalize ${biasBadge(active.bias)}`}>{active.bias}</span>
              <span className="rounded-full border border-slate-600 bg-slate-800/60 px-2 py-0.5 text-[11px] font-semibold capitalize text-slate-300">{active.position}</span>
              <Button onClick={closeActive} disabled={closing} variant="outline" size="sm" className="h-7 gap-1 border-red-500/40 text-red-300 hover:bg-red-500/10">
                {closing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />}Close
              </Button>
            </div>
          </div>

          <PerfHeadline perf={active.perf} position={active.position} />

          <p className="mt-4 text-[13px] leading-relaxed text-slate-300">{active.thesis}</p>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div>
              <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-500">Exit plan</p>
              <div className="space-y-1.5">
                {(active.targets || []).map((t, i) => <TargetRow key={i} t={t} position={active.position} />)}
                {active.stop && (
                  <div className={`flex items-center gap-2 rounded-lg border px-2.5 py-2 ${active.stop.hit ? 'border-red-500/50 bg-red-500/10' : 'border-red-500/30 bg-red-500/5'}`}>
                    <ShieldAlert className="h-3.5 w-3.5 text-red-400" />
                    <span className="text-[13px] font-semibold text-slate-100">Stop</span>
                    <span className="text-[13px] font-bold text-red-300">{fmtUsd(active.stop.price)}</span>
                    <span className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-bold ${active.stop.hit ? 'bg-red-500/20 text-red-300' : 'bg-slate-800 text-slate-500'}`}>{active.stop.hit ? 'HIT' : 'ARMED'}</span>
                  </div>
                )}
              </div>
              <p className="mb-1.5 mt-4 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-500"><Bell className="h-3 w-3" />Nudge rules</p>
              <div className="space-y-1.5">{(active.rules || []).map((r, i) => <RuleRow key={i} r={r} />)}</div>
            </div>
            <div>
              <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-500">Albert&apos;s log</p>
              <EventTimeline events={active.events} />
            </div>
          </div>
        </Card>
      ) : (
        <Card className="border-0 bg-gradient-to-br from-sky-500/[0.07] to-slate-900 p-6 ring-1 ring-sky-500/25">
          <div className="flex items-center gap-3">
            <img src="/albert.png" alt="Albert" className="h-11 w-11 rounded-full object-cover ring-2 ring-sky-500/40" />
            <div>
              <h3 className="text-lg font-black text-white">Let Albert build you a {coinName} strategy</h3>
              <p className="text-[13px] text-slate-400">He&apos;ll draft a full plan from the live dashboard — then track it and nudge you.</p>
            </div>
          </div>
          {data?.just_closed && (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 text-[12px] text-slate-300">
              <Check className="h-4 w-4 text-emerald-400" />Your last strategy just closed at <span className={`font-bold ${pnlColor(data.just_closed.final_pnl_pct)}`}>{data.just_closed.final_pnl_pct > 0 ? '+' : ''}{data.just_closed.final_pnl_pct}%</span> — see it in history below.
            </div>
          )}
          <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={2}
            placeholder={`Optional: describe your goal — e.g. "medium-risk swing long over a month", "fade the pump", "accumulate on dips"…`}
            className="mt-4 w-full resize-none rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:border-sky-500/50 focus:outline-none" />
          <div className="mt-3 flex flex-wrap gap-2">
            <Button onClick={build} disabled={building} className="gap-1.5 bg-gradient-to-r from-sky-500 to-violet-500 hover:opacity-90">
              {building ? <><Loader2 className="h-4 w-4 animate-spin" />Albert is drafting…</> : <><Sparkles className="h-4 w-4" />Build me a strategy</>}
            </Button>
            {['Swing long over a month', 'Fade the pump (short)', 'Accumulate on dips'].map((g) => (
              <button key={g} onClick={() => setGoal(g)} className="rounded-full border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs text-slate-300 hover:border-sky-500/40 hover:text-sky-300">{g}</button>
            ))}
          </div>
        </Card>
      )}

      {/* History */}
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <History className="h-4 w-4 text-slate-400" />
          <h3 className="text-sm font-bold text-white">Past {coinName} strategies</h3>
          {stats.total > 0 && (
            <div className="ml-auto flex items-center gap-2 text-[11px]">
              <span className="flex items-center gap-1 rounded-full border border-slate-700 bg-slate-900/60 px-2 py-0.5 text-slate-300"><Trophy className="h-3 w-3 text-amber-400" />{stats.win_rate}% win rate</span>
              <span className="rounded-full border border-slate-700 bg-slate-900/60 px-2 py-0.5 text-slate-300">{stats.wins}W · {stats.losses}L</span>
              {stats.avg_pnl_pct != null && <span className={`rounded-full border border-slate-700 bg-slate-900/60 px-2 py-0.5 font-semibold ${pnlColor(stats.avg_pnl_pct)}`}>avg {stats.avg_pnl_pct > 0 ? '+' : ''}{stats.avg_pnl_pct}%</span>}
            </div>
          )}
        </div>
        {history.length ? (
          <div className="space-y-2">{history.map((s) => <HistoryCard key={s.id} s={s} />)}</div>
        ) : (
          <Card className="border-0 bg-slate-900/40 p-6 text-center ring-1 ring-slate-800">
            <p className="text-sm text-slate-500">No past strategies for {coinName} yet. Build one above and Albert will start keeping score.</p>
          </Card>
        )}
      </div>

      {draft && (
        <DraftModal draft={draft} symbol={symbol} regenerating={building}
          onClose={() => setDraft(null)}
          onRegenerate={build}
          onActivated={(s) => { setDraft(null); setGoal(''); load(); }} />
      )}
    </div>
  );
}
