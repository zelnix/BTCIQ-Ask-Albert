'use client';
// Trader Home cockpit — the plain-first landing view. Consumes the deterministic
// GET /api/v1/albert/trader-home aggregation and renders a 3-second hierarchy:
// (1) the signal + conviction, (2) an executive briefing, (3) the evidence
// (drivers/confluence/historical edge), plus the user's portfolio impact and an
// honest integrity strip. Advisory / paper only.
import React from 'react';
import { API_BASE, getPid } from '../lib/api';
import {
  Loader2, TrendingUp, TrendingDown, Minus, ShieldCheck, Activity, Gauge,
  CheckCircle2, AlertTriangle, Layers, Clock, ArrowRight,
} from 'lucide-react';

const callTone = (call) => {
  const c = (call || '').toLowerCase();
  if (c.includes('bull') || c.includes('buy') || c.includes('long')) return { fg: 'text-emerald-300', bg: 'bg-emerald-500/10', ring: 'ring-emerald-500/30', Icon: TrendingUp };
  if (c.includes('bear') || c.includes('sell') || c.includes('short')) return { fg: 'text-rose-300', bg: 'bg-rose-500/10', ring: 'ring-rose-500/30', Icon: TrendingDown };
  return { fg: 'text-slate-200', bg: 'bg-slate-500/10', ring: 'ring-slate-500/30', Icon: Minus };
};

const fmtUsd = (n) => (n == null ? '—' : '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }));

export default function TraderHome({ symbol = 'BTC', onNav }) {
  const [d, setD] = React.useState(null);
  const [err, setErr] = React.useState(false);
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
  const up = (mkt.change24h || 0) >= 0;

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
            <p className={`text-[12px] font-semibold ${up ? 'text-emerald-400' : 'text-rose-400'}`}>{up ? '+' : ''}{mkt.change24h ?? '—'}% 24h</p>
            {sig.conviction != null && (
              <p className="mt-0.5 flex items-center justify-end gap-1 text-[10px] text-slate-500"><Gauge className="h-3 w-3" />Conviction {Math.round(sig.conviction)}/100</p>
            )}
          </div>
        </div>
        {sig.circuitBreaker && String(sig.circuitBreaker).toLowerCase() !== 'normal' && (
          <div className="mt-3 flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[11px] font-semibold text-amber-300"><AlertTriangle className="h-3.5 w-3.5" />Circuit breaker: {sig.circuitBreaker}</div>
        )}
      </div>

      {/* 2) Executive briefing */}
      {d.executiveBrief && (d.executiveBrief.points || []).length > 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
          <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><Activity className="h-3.5 w-3.5 text-sky-300" />Executive briefing</p>
          <p className="text-[13px] leading-relaxed text-slate-200">{d.executiveBrief.points[0]}</p>
          {onNav && <button onClick={() => onNav('strategies')} className="mt-2 flex items-center gap-1 text-[11px] font-semibold text-sky-400 hover:text-sky-300">Open the Command Centre <ArrowRight className="h-3 w-3" /></button>}
        </div>
      )}

      {/* 3) Evidence: drivers + confluence + historical edge */}
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
                  <span className="w-8 shrink-0 text-right text-[11px] font-mono text-slate-400">{dr.score != null ? Math.round(dr.score) : '—'}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {edge && (
          <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400"><ShieldCheck className="h-3.5 w-3.5 text-emerald-300" />Historical edge</p>
            <div className="grid grid-cols-2 gap-2 text-[12px]">
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2"><p className="text-slate-500">Brier</p><p className="font-mono text-slate-200">{edge.brier ?? '—'}</p></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2"><p className="text-slate-500">Ann. Sharpe</p><p className="font-mono text-slate-200">{edge.sharpe ?? '—'}</p></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2"><p className="text-slate-500">PSR</p><p className="font-mono text-slate-200">{edge.psr ?? '—'}</p></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2"><p className="text-slate-500">Trades</p><p className="font-mono text-slate-200">{edge.nTrades ?? '—'}</p></div>
            </div>
            <p className="mt-2 text-[10px] text-slate-600">{edge.note}</p>
          </div>
        )}
      </div>

      {/* Portfolio impact + integrity */}
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
