'use client';
import React from 'react';
import { API_BASE, getPid } from '../lib/api';
import { Loader2, X, TrendingUp, TrendingDown, ShieldCheck, ShieldAlert, ArrowRight, Star, Sparkles, Compass, Target } from 'lucide-react';

const fmt = (n) => (n == null || isNaN(n)) ? '—' : '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
const CALL_COLOR = {
  BUY: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  HOLD: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
  SELL: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
  WAIT: 'bg-slate-700/40 text-slate-300 border-slate-600',
};

function greetingWord() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

export default function WelcomeBrief({ onClose, onOpenCommandCentre }) {
  const [data, setData] = React.useState(null);
  const [err, setErr] = React.useState(false);

  React.useEffect(() => {
    const pid = getPid();
    fetch(`${API_BASE}/v1/albert/welcome-brief?pid=${encodeURIComponent(pid || '')}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => { if (j && (j.status === 'ready')) setData(j); else setErr(true); })
      .catch(() => setErr(true));
  }, []);

  const dateStr = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
  const name = data?.name;
  const counts = data?.callCounts || {};
  const buys = data?.topBuys || [];
  const sells = data?.topSells || [];
  const watch = data?.watchlist || [];
  const prot = data?.protection || {};

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="max-h-[88vh] w-full max-w-md overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="relative overflow-hidden rounded-t-2xl border-b border-slate-800 bg-gradient-to-br from-sky-500/15 via-violet-500/10 to-slate-900 p-4">
          <button onClick={onClose} className="absolute right-3 top-3 text-slate-400 hover:text-white"><X className="h-4 w-4" /></button>
          <div className="flex items-center gap-3">
            <img src="/albert.png" alt="Albert" className="h-11 w-11 rounded-full ring-2 ring-sky-500/40" />
            <div>
              <p className="text-[11px] uppercase tracking-wide text-sky-300">{dateStr}</p>
              <h3 className="text-lg font-bold text-white">{greetingWord()}{name ? `, ${name}` : ''}</h3>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="space-y-3 p-4">
          {!data && !err && (
            <div className="flex items-center gap-2 py-10 text-[12px] text-slate-400"><Loader2 className="h-4 w-4 animate-spin" />Albert is preparing your brief…</div>
          )}
          {err && (
            <p className="py-8 text-center text-[12px] text-slate-500">Couldn&apos;t load your brief right now. You can head straight into the dashboard.</p>
          )}

          {data && (
            <>
              {/* Albert's character-driven line */}
              {data.albertLine && (
                <div className="flex items-start gap-2 rounded-xl border border-violet-500/25 bg-violet-500/[0.06] p-3">
                  <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-300" />
                  <p className="text-[13px] italic leading-relaxed text-slate-200">{data.albertLine}</p>
                </div>
              )}

              {data.onboarding ? (
                /* Onboarding nudge */
                <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.06] p-3">
                  <div className="mb-1 flex items-center gap-1.5 text-[12px] font-bold text-amber-200"><Target className="h-3.5 w-3.5" />Set your Trading Mandate</div>
                  <p className="text-[12px] text-slate-300">Tell Albert your goals, risk limits and protected reserve, and he&apos;ll turn the market into a personalized plan every morning — sizing, entries and exits included.</p>
                </div>
              ) : (
                <>
                  {/* Portfolio snapshot */}
                  <div className="grid grid-cols-3 gap-2">
                    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-2.5">
                      <p className="text-[9px] uppercase tracking-wide text-slate-500">Portfolio</p>
                      <p className="mt-0.5 text-sm font-bold text-white">{fmt(data.portfolio?.totalValueUsd)}</p>
                    </div>
                    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-2.5">
                      <p className="text-[9px] uppercase tracking-wide text-slate-500">Deployable</p>
                      <p className="mt-0.5 text-sm font-bold text-emerald-300">{fmt(data.portfolio?.deployableUsdcUsd)}</p>
                    </div>
                    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-2.5">
                      <p className="text-[9px] uppercase tracking-wide text-slate-500">Protection</p>
                      <p className={`mt-0.5 flex items-center gap-1 text-sm font-bold ${prot.active ? 'text-rose-300' : 'text-slate-300'}`}>
                        {prot.active ? <ShieldAlert className="h-3.5 w-3.5" /> : <ShieldCheck className="h-3.5 w-3.5" />}
                        {prot.active ? 'On' : 'Off'}
                      </p>
                    </div>
                  </div>

                  {/* Albert's calls today */}
                  <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-300"><Compass className="h-3.5 w-3.5 text-sky-300" />Albert&apos;s calls today</p>
                      <div className="flex items-center gap-1.5 text-[10px]">
                        <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 font-bold text-emerald-300">{counts.BUY || 0} BUY</span>
                        <span className="rounded-full border border-rose-500/40 bg-rose-500/10 px-1.5 py-0.5 font-bold text-rose-300">{counts.SELL || 0} SELL</span>
                        <span className="rounded-full border border-sky-500/40 bg-sky-500/10 px-1.5 py-0.5 font-bold text-sky-300">{counts.HOLD || 0} HOLD</span>
                      </div>
                    </div>
                    {(buys.length === 0 && sells.length === 0) ? (
                      <p className="text-[12px] text-slate-500">No actionable calls this morning — Albert is staying patient.</p>
                    ) : (
                      <div className="space-y-1.5">
                        {buys.map((b) => (
                          <div key={'b' + b.symbol} className="flex items-center justify-between text-[12px]">
                            <span className="flex items-center gap-1.5"><TrendingUp className="h-3.5 w-3.5 text-emerald-400" /><b className="text-slate-200">{b.symbol}</b> <span className="text-slate-500">score {b.score}</span></span>
                            <span className="text-emerald-300">{fmt(b.deployNowUsd)} now</span>
                          </div>
                        ))}
                        {sells.map((s) => (
                          <div key={'s' + s.symbol} className="flex items-center justify-between text-[12px]">
                            <span className="flex items-center gap-1.5"><TrendingDown className="h-3.5 w-3.5 text-rose-400" /><b className="text-slate-200">{s.symbol}</b> <span className="text-slate-500">{s.action === 'EXIT_100' ? 'exit 100%' : (s.action || '').replace('TRIM_', 'trim ') + (s.action ? '%' : '')}</span></span>
                            <span className="text-rose-300">{fmt(s.sellUsd)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Watchlist highlights */}
                  {watch.length > 0 && (
                    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                      <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-amber-200"><Star className="h-3.5 w-3.5" fill="currentColor" />Your watchlist</p>
                      <div className="flex flex-wrap gap-1.5">
                        {watch.map((w) => (
                          <span key={w.symbol} className="flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-900/60 py-0.5 pl-2 pr-1.5 text-[11px]">
                            <b className="text-slate-200">{w.symbol}</b>
                            <span className={`rounded-full border px-1.5 py-0 text-[9px] font-bold ${CALL_COLOR[w.albertCall] || CALL_COLOR.WAIT}`}>{w.albertCall}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}

              <p className="text-center text-[10px] text-slate-600">Advisory / paper only — Albert explains, he doesn&apos;t place live trades.</p>
            </>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex items-center gap-2 border-t border-slate-800 p-3">
          <button onClick={onClose} className="flex-1 rounded-xl border border-slate-700 px-3 py-2 text-[12px] font-semibold text-slate-300 hover:bg-slate-800">Dismiss</button>
          <button onClick={onOpenCommandCentre} className="flex flex-[1.4] items-center justify-center gap-1.5 rounded-xl bg-sky-500 px-3 py-2 text-[12px] font-bold text-white hover:bg-sky-400">
            {data?.onboarding ? 'Set up my mandate' : 'Open the Command Centre'}<ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
