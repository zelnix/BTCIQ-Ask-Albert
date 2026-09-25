'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  Crosshair, Plus, Loader2, Sparkles, ShieldCheck, ChevronDown, Play, Pause, Archive,
  Link2, Unlink, FlaskConical, CheckCircle2, AlertTriangle, ArrowRight, X,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { API_BASE } from '../lib/api';

const idem = () => 'k_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
const post = (path, body) => fetch(`${API_BASE}${path}`, {
  method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body || {}),
});
const get = (path) => fetch(`${API_BASE}${path}`, { credentials: 'include', cache: 'no-store' });

const STATE_COLOR = {
  REVIEWED: 'text-sky-300', PAPER_ASSIGNED: 'text-amber-300', PAPER_ACTIVE: 'text-emerald-300',
  PAUSED: 'text-orange-300', ARCHIVED: 'text-slate-500',
};

function ConfirmBtn({ label, icon: Icon, onConfirm, tone = 'sky', busy }) {
  const [armed, setArmed] = useState(false);
  const colors = { sky: 'bg-sky-500 hover:bg-sky-400', emerald: 'bg-emerald-600 hover:bg-emerald-500',
    amber: 'bg-amber-600 hover:bg-amber-500', red: 'bg-red-600 hover:bg-red-500', slate: 'bg-slate-700 hover:bg-slate-600' };
  if (armed) {
    return (
      <span className="inline-flex items-center gap-1">
        <Button size="sm" disabled={busy} onClick={() => { setArmed(false); onConfirm(); }} className={`h-7 gap-1 px-2.5 text-[12px] ${colors[tone]}`}>
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}Confirm {label}
        </Button>
        <button onClick={() => setArmed(false)} className="rounded p-1 text-slate-400 hover:text-white"><X className="h-3.5 w-3.5" /></button>
      </span>
    );
  }
  return (
    <Button size="sm" variant="outline" onClick={() => setArmed(true)} className="h-7 gap-1 border-slate-700 px-2.5 text-[12px] text-slate-200 hover:bg-slate-800">
      {Icon && <Icon className="h-3.5 w-3.5" />}{label}
    </Button>
  );
}

function Builder({ onSaved, onCancel }) {
  const [goal, setGoal] = useState('');
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState(null);
  const [review, setReview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const runDraft = async () => {
    if (!goal.trim()) return;
    setDrafting(true); setErr('');
    try {
      const j = await (await post('/v1/albert/studio/draft', { goal })).json();
      setDraft(j.draft); setReview({ contract: j.contract, hash: j.contractHash, summary: j.summary, errors: j.validationErrors });
    } catch (e) { setErr('Could not draft — try again.'); }
    finally { setDrafting(false); }
  };
  const revalidate = async (d) => {
    const j = await (await post('/v1/albert/studio/validate', { draft: d })).json();
    setReview({ contract: j.contract, hash: j.contractHash, summary: j.summary, errors: j.validationErrors });
  };
  const setAsset = (i, key, val) => {
    const next = { ...draft, assets: draft.assets.map((a, ix) => ix === i ? { ...a, [key]: key === 'weightPct' ? Number(val) : val.toUpperCase() } : a) };
    setDraft(next); revalidate(next);
  };
  const addAsset = () => { const next = { ...draft, assets: [...(draft.assets || []), { symbol: '', weightPct: 0 }] }; setDraft(next); };
  const removeAsset = (i) => { const next = { ...draft, assets: draft.assets.filter((_, ix) => ix !== i) }; setDraft(next); revalidate(next); };
  const setField = (k, v) => { const next = { ...draft, [k]: v }; setDraft(next); };

  const save = async () => {
    setBusy(true); setErr('');
    try {
      const r = await post('/v1/albert/studio/save', { draft, name: draft.name, confirm: true,
        idempotencyKey: idem(), expectedHash: review.hash });
      const j = await r.json();
      if (r.ok) onSaved(j.strategyId);
      else setErr(j.detail || 'Save failed.');
    } catch (e) { setErr('Save failed.'); }
    finally { setBusy(false); }
  };

  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="mb-3 flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-violet-400" />
        <h3 className="text-sm font-bold text-white">Build a strategy with Albert</h3>
        <button onClick={onCancel} className="ml-auto rounded p-1 text-slate-400 hover:text-white"><X className="h-4 w-4" /></button>
      </div>
      {!draft && (
        <div>
          <p className="mb-2 text-[13px] text-slate-400">Describe your objective — assets, timeframe, entries, exits, profit-taking, risk. Albert drafts a structured plan for you to review.</p>
          <textarea rows={4} value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="e.g. A swing basket of SOL, NEAR and FIL weighted 40/30/30, buy pullbacks to the 20-day average, trail stops, 20% reserve."
            className="w-full resize-none rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-violet-500" />
          <Button onClick={runDraft} disabled={drafting || !goal.trim()} className="mt-3 gap-1.5 bg-violet-600 hover:bg-violet-500">
            {drafting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}Draft with Albert
          </Button>
        </div>
      )}
      {draft && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="text-[12px] text-slate-400">Name
              <input value={draft.name || ''} onChange={(e) => setField('name', e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm text-white outline-none focus:border-sky-500" /></label>
            <label className="text-[12px] text-slate-400">Timeframe
              <input value={draft.timeframe || ''} onChange={(e) => setField('timeframe', e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm text-white outline-none focus:border-sky-500" /></label>
          </div>
          <div>
            <p className="mb-1 text-[12px] font-semibold text-slate-400">Assets &amp; weights</p>
            <div className="space-y-1.5">
              {(draft.assets || []).map((a, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input value={a.symbol} onChange={(e) => setAsset(i, 'symbol', e.target.value)} placeholder="SYM" className="w-24 rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm font-semibold text-white outline-none focus:border-sky-500" />
                  <input type="number" value={a.weightPct} onChange={(e) => setAsset(i, 'weightPct', e.target.value)} className="w-24 rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm text-white outline-none focus:border-sky-500" />
                  <span className="text-[12px] text-slate-500">%</span>
                  <button onClick={() => removeAsset(i)} className="rounded p-1 text-slate-500 hover:text-red-400"><X className="h-3.5 w-3.5" /></button>
                </div>
              ))}
            </div>
            <button onClick={addAsset} className="mt-1.5 inline-flex items-center gap-1 text-[12px] font-semibold text-sky-400 hover:text-sky-300"><Plus className="h-3.5 w-3.5" />Add asset</button>
          </div>
          {['entryRules', 'exitRules', 'profitTaking', 'invalidation'].map((k) => (
            <label key={k} className="block text-[12px] text-slate-400 capitalize">{k.replace(/([A-Z])/g, ' $1')}
              <textarea rows={1} value={draft[k] || ''} onChange={(e) => setField(k, e.target.value)} className="mt-1 w-full resize-none rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm text-slate-200 outline-none focus:border-sky-500" /></label>
          ))}
          {review && (
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
              <p className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400"><ShieldCheck className="h-3.5 w-3.5" />Review · hash {review.hash}</p>
              <p className="text-[13px] text-slate-200">{review.summary}</p>
              {(review.errors || []).length > 0 && (
                <ul className="mt-2 space-y-0.5 text-[12px] text-red-400">
                  {review.errors.map((e, i) => <li key={i} className="flex items-start gap-1.5"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{e}</li>)}
                </ul>
              )}
            </div>
          )}
          {err && <p className="text-[12px] font-medium text-red-400">{err}</p>}
          <div className="flex items-center gap-2">
            <ConfirmBtn label="Save strategy" icon={CheckCircle2} tone="emerald" busy={busy}
              onConfirm={save} />
            <span className="text-[11px] text-slate-500">Saves the EXACT reviewed contract as an immutable version.</span>
          </div>
        </div>
      )}
    </Card>
  );
}

function Methodology({ bt, contractHash }) {
  // M-F: methodology, hashes and cost assumptions are COLLAPSED (not removed) so the
  // result stays readable while every integrity value remains one click away.
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button onClick={() => setOpen((o) => !o)} className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500 hover:text-slate-300">
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />Methodology, costs &amp; integrity
      </button>
      {open && (
        <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-lg border border-slate-800 bg-slate-950/60 p-2.5 text-[11px] sm:grid-cols-3">
          {[['Benchmark', bt.benchmark], ['Fees paid', `$${bt.feesPaidUsd}`], ['Slippage', `${bt.slippageBps} bps`],
            ['Data coverage', `${bt.dataCoveragePct}%`], ['Sample', `${bt.sampleSizeDays} days`],
            ['Backtest version', bt.backtestVersion], ['Contract hash', contractHash], ['Data hash', bt.dataHash]].map(([k, v]) => (
            <div key={k} className="min-w-0">
              <span className="block text-[10px] uppercase tracking-wide text-slate-500">{k}</span>
              <span className="block truncate font-mono font-semibold text-slate-200" title={String(v)}>{v == null ? '—' : String(v)}</span>
            </div>
          ))}
          <p className="col-span-full text-[10px] leading-relaxed text-slate-500">
            Deterministic historical replay of daily candles, bound to this exact contract version and data snapshot — the same inputs always produce the same result, and Albert never manufactures these numbers.
          </p>
        </div>
      )}
    </div>
  );
}

function Detail({ sid, onChange }) {
  const [s, setS] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [acct, setAcct] = useState('');
  const [bt, setBt] = useState(null);
  const [btBusy, setBtBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    const j = await (await get(`/v1/albert/studio/strategies/${sid}`)).json();
    setS(j); setBt(j.backtest || null);
  }, [sid]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { get('/v1/albert/paper/accounts').then((r) => r.json()).then((j) => setAccounts(j.accounts || [])).catch(() => {}); }, []);

  const runBt = async () => {
    setBtBusy(true);
    try { const j = await (await post(`/v1/albert/studio/strategies/${sid}/backtest`, {})).json(); setBt(j.backtest); }
    finally { setBtBusy(false); }
  };
  const doCmd = async (cmd, extra) => {
    setBusy(true); setErr('');
    try {
      const r = await post(`/v1/albert/studio/strategies/${sid}/${cmd}`, { confirm: true, idempotencyKey: idem(),
        expectedVersion: s.version, ...(extra || {}) });
      const j = await r.json();
      if (r.ok) { await load(); onChange && onChange(); }
      else setErr(j.detail || `${cmd} failed.`);
    } catch (e) { setErr(`${cmd} failed.`); }
    finally { setBusy(false); }
  };

  if (!s) return <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800"><Loader2 className="h-5 w-5 animate-spin text-slate-400" /></Card>;
  const st = s.lifecycleState;
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="text-base font-bold text-white">{s.name}</h3>
        <Badge variant="outline" className={`border-slate-700 text-[11px] ${STATE_COLOR[st] || 'text-slate-300'}`}>{(st || '').replace(/_/g, ' ')}</Badge>
        <span className="text-[11px] text-slate-500">v{s.version}</span>
      </div>
      <p className="text-[13px] text-slate-300">{s.summary}</p>

      <div className="mt-3 overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full text-[13px]">
          <thead className="bg-slate-950/60 text-[10px] uppercase tracking-wider text-slate-500"><tr><th className="px-3 py-1.5 text-left">Asset</th><th className="px-3 py-1.5 text-right">Weight</th></tr></thead>
          <tbody>
            {(s.contract?.assets || []).map((a) => (
              <tr key={a.symbol} className="border-t border-slate-800/70"><td className="px-3 py-1.5 font-semibold text-slate-200">{a.symbol}</td><td className="px-3 py-1.5 text-right font-mono text-slate-300">{a.weightPct}%</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Backtest */}
      <div className="mt-4">
        <div className="flex items-center gap-2">
          <p className="flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-wider text-slate-400"><FlaskConical className="h-3.5 w-3.5" />Backtest</p>
          <Button size="sm" onClick={runBt} disabled={btBusy} className="ml-auto h-7 gap-1 bg-slate-700 px-2.5 text-[12px] hover:bg-slate-600">{btBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}Run backtest</Button>
        </div>
        {bt && !bt.error && (
          <div className="mt-2 space-y-2">
            {/* Decision-useful results stay in plain sight. */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[['Strategy return', `${bt.totalReturnPct}%`],
                ['Bitcoin over the same period', `${bt.benchmarkReturnPct}%`],
                ['Worst drawdown', `${bt.maxDrawdownPct}%`],
                ['Tested period', `${bt.sampleSizeDays} days · ${bt.dataCoveragePct}% covered`]].map(([l, v]) => (
                <div key={l} className="rounded-lg border border-slate-800 bg-slate-950/50 p-2.5">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">{l}</p>
                  <p className="text-sm font-bold text-white">{v}</p>
                </div>
              ))}
            </div>
            <p className="max-w-[80ch] text-[12.5px] leading-relaxed text-slate-300">
              Over the last {bt.sampleSizeDays} days this plan would have returned {bt.totalReturnPct}% versus {bt.benchmarkReturnPct}% for simply holding Bitcoin, with a worst peak-to-trough fall of {bt.maxDrawdownPct}%. Trading costs are already deducted. Past behaviour is not a promise.
            </p>
            <Methodology bt={bt} contractHash={s.contractHash} />
          </div>
        )}
        {bt && bt.error && <p className="mt-2 text-[12px] text-amber-400">No historical data available for these assets right now.</p>}
      </div>

      {/* Lifecycle */}
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-800 pt-3">
        {st === 'REVIEWED' && (
          <>
            <select value={acct} onChange={(e) => setAcct(e.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-[12px] text-slate-200">
              <option value="">Choose paper account…</option>
              {accounts.map((a) => <option key={a.paperAccountId} value={a.paperAccountId}>{a.name}</option>)}
            </select>
            <ConfirmBtn label="Assign" icon={Link2} tone="amber" busy={busy} onConfirm={() => acct && doCmd('assign', { paperAccountId: acct })} />
            <ConfirmBtn label="Archive" icon={Archive} tone="slate" busy={busy} onConfirm={() => doCmd('archive')} />
          </>
        )}
        {st === 'PAPER_ASSIGNED' && (<>
          <ConfirmBtn label="Activate" icon={Play} tone="emerald" busy={busy} onConfirm={() => doCmd('activate')} />
          <ConfirmBtn label="Unassign" icon={Unlink} tone="slate" busy={busy} onConfirm={() => doCmd('unassign')} />
        </>)}
        {st === 'PAPER_ACTIVE' && (<>
          <ConfirmBtn label="Pause" icon={Pause} tone="amber" busy={busy} onConfirm={() => doCmd('pause')} />
          <ConfirmBtn label="Close" icon={X} tone="slate" busy={busy} onConfirm={() => doCmd('close')} />
        </>)}
        {st === 'PAUSED' && (<>
          <ConfirmBtn label="Activate" icon={Play} tone="emerald" busy={busy} onConfirm={() => doCmd('activate')} />
          <ConfirmBtn label="Archive" icon={Archive} tone="slate" busy={busy} onConfirm={() => doCmd('archive')} />
        </>)}
        {s.assignedPaperAccountId && <span className="text-[11px] text-slate-500">Assigned · availability only — assigning never places a trade.</span>}
      </div>
      {err && <p className="mt-2 text-[12px] font-medium text-red-400">{err}</p>}
    </Card>
  );
}

export default function StrategyStudio() {
  const [list, setList] = useState([]);
  const [sel, setSel] = useState(null);
  const [building, setBuilding] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { const j = await (await get('/v1/albert/studio/strategies')).json(); setList(j.strategies || []); }
    catch (e) { /* noop */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2.5">
        <Crosshair className="h-5 w-5 text-violet-400" />
        <h1 className="text-lg font-bold text-white">Strategies</h1>
        <span className="text-[12px] text-slate-500">Plans you build with Albert · paper only</span>
        <Button size="sm" onClick={() => { setBuilding(true); setSel(null); }} className="ml-auto gap-1.5 bg-violet-600 hover:bg-violet-500"><Plus className="h-4 w-4" />New with Albert</Button>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-2 lg:col-span-1">
          {loading && <p className="text-[13px] text-slate-500">Loading…</p>}
          {!loading && list.length === 0 && !building && (
            <Card className="border-0 border-dashed bg-slate-900 p-5 text-center ring-1 ring-slate-800">
              <p className="text-[13px] text-slate-400">No strategies yet. Build your first with Albert.</p>
              <Button size="sm" onClick={() => setBuilding(true)} className="mt-3 gap-1.5 bg-violet-600 hover:bg-violet-500"><Plus className="h-4 w-4" />New with Albert</Button>
            </Card>
          )}
          {list.map((s) => (
            <button key={s.strategyId} onClick={() => { setSel(s.strategyId); setBuilding(false); }}
              className={`w-full rounded-lg border p-3 text-left transition-colors ${sel === s.strategyId ? 'border-violet-500/50 bg-violet-500/[0.06]' : 'border-slate-800 bg-slate-900 hover:border-slate-700'}`}>
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-sm font-semibold text-white">{s.name}</p>
                <Badge variant="outline" className={`shrink-0 border-slate-700 text-[10px] ${STATE_COLOR[s.lifecycleState] || 'text-slate-300'}`}>{(s.lifecycleState || '').replace(/_/g, ' ')}</Badge>
              </div>
              <p className="mt-1 truncate text-[12px] text-slate-500">{(s.contract?.assets || []).map((a) => a.symbol).join(' · ')} · v{s.version}</p>
            </button>
          ))}
        </div>
        <div className="lg:col-span-2">
          {building ? <Builder onCancel={() => setBuilding(false)} onSaved={(sid) => { setBuilding(false); load(); setSel(sid); }} />
            : sel ? <Detail sid={sel} onChange={load} />
            : <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800"><p className="text-[13px] text-slate-400">Select a strategy, or build a new one with Albert.</p></Card>}
        </div>
      </div>
      <p className="pt-1 text-center text-[11px] text-slate-600">Paper trading only. Saving stores the exact reviewed contract as an immutable, hashed version. Assigning makes it available to the paper engine — it never places a trade.</p>
    </div>
  );
}
