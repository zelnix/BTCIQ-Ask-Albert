'use client';

import React from 'react';
import { API_BASE, getPid } from '../lib/api';
import { Button } from '@/components/ui/button';
import { ShieldCheck, Wallet, Target, Plus, Trash2, Loader2, Check, ChevronDown } from 'lucide-react';

const fmt = (n) => (n == null || isNaN(n)) ? '—' : '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });

function ActionPill({ a }) {
  const map = { BUY: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40', HOLD: 'bg-sky-500/15 text-sky-300 border-sky-500/40', SELL: 'bg-rose-500/15 text-rose-300 border-rose-500/40', WAIT: 'bg-slate-700/40 text-slate-300 border-slate-600' };
  return <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${map[a] || map.WAIT}`}>{a}</span>;
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
                <th className="pr-2">Conf</th><th className="pr-2">Deploy now</th><th className="pr-2">Planned</th><th className="pr-3"></th></tr></thead>
              <tbody>
                {decisions.decisions.map((d) => (
                  <React.Fragment key={d.symbol}>
                    <tr className="border-t border-slate-800/60 hover:bg-slate-900/40">
                      <td className="py-1.5 pl-3 pr-2 font-semibold text-slate-200">{d.symbol}</td>
                      <td className="pr-2"><ActionPill a={d.action} /></td>
                      <td className="pr-2 text-slate-300">{d.opportunityScore}</td>
                      <td className="pr-2 text-slate-400">{d.confidence}%</td>
                      <td className="pr-2 text-emerald-400">{d.recommendedDeployNowUsd ? fmt(d.recommendedDeployNowUsd) : '—'}</td>
                      <td className="pr-2 text-slate-400">{d.totalPlannedDeploymentUsd ? fmt(d.totalPlannedDeploymentUsd) : '—'}</td>
                      <td className="pr-3 text-right"><button onClick={() => setExpanded(expanded === d.symbol ? null : d.symbol)} className="text-slate-500 hover:text-slate-200"><ChevronDown className={`h-4 w-4 transition-transform ${expanded === d.symbol ? 'rotate-180' : ''}`} /></button></td>
                    </tr>
                    {expanded === d.symbol && (
                      <tr className="border-t border-slate-800/40 bg-slate-950/40"><td colSpan={7} className="px-3 py-2">
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <div>
                            <p className="mb-1 text-[10px] uppercase text-slate-500">Why</p>
                            <ul className="space-y-0.5 text-[11px] text-slate-300">{(d.reasons || []).map((r, i) => <li key={i}>• {r}</li>)}</ul>
                            {(d.warnings || []).map((w, i) => <p key={i} className="mt-1 text-[11px] text-amber-400">⚠ {w}</p>)}
                            {d.invalidationPrice ? <p className="mt-1 text-[11px] text-rose-400">Invalidation ≈ {fmt(d.invalidationPrice)}</p> : null}
                          </div>
                          <div>
                            <p className="mb-1 text-[10px] uppercase text-slate-500">Score breakdown</p>
                            <div className="flex flex-wrap gap-1">{Object.entries(d.scoreComponents || {}).map(([k, v]) => <span key={k} className="rounded-full border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400">{k} {v}</span>)}</div>
                            {(d.tranches && d.tranches.length > 0) && (<div className="mt-2"><p className="mb-1 text-[10px] uppercase text-slate-500">Tranche plan</p>{d.tranches.map((t) => <div key={t.number} className="flex justify-between text-[11px] text-slate-300"><span>T{t.number} · {t.pct}% · {t.trigger.replace(/_/g, ' ').toLowerCase()}</span><span className="text-slate-400">{fmt(t.amountUsd)}</span></div>)}</div>)}
                          </div>
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
    </div>
  );
}
