'use client';
// Weekly Brief — a Sunday recap of the past week's Albert call changes, paper
// fills and drawdown recoveries. Deterministic aggregation from
// GET /api/v1/albert/weekly-brief plus ONE character-driven line (read-only LLM).
// Rendered as a Sunday modal (default export) and as an inline dashboard card
// (WeeklyBriefCard).
import React from 'react';
import { API_BASE, getPid } from '../lib/api';
import { Loader2, X, TrendingUp, TrendingDown, ShieldCheck, ArrowRight, Sparkles, CalendarDays, Repeat, Activity } from 'lucide-react';

const fmt = (n) => (n == null || isNaN(n)) ? '—' : '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });

function useWeeklyBrief() {
  const [data, setData] = React.useState(null);
  const [err, setErr] = React.useState(false);
  React.useEffect(() => {
    const pid = getPid();
    if (!pid) { setData({ status: 'ready', empty: true, calls: {}, fills: {}, recoveries: {} }); return; }
    fetch(`${API_BASE}/v1/albert/weekly-brief?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => { if (j && j.status === 'ready') setData(j); else setErr(true); })
      .catch(() => setErr(true));
  }, []);
  return { data, err };
}

function StatTrio({ data }) {
  const calls = data?.calls || {};
  const fills = data?.fills || {};
  const recoveries = data?.recoveries || {};
  return (
    <div className="grid grid-cols-3 gap-2">
      <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-2.5 text-center">
        <p className="flex items-center justify-center gap-1 text-[9px] uppercase tracking-wide text-slate-500"><Activity className="h-3 w-3" />Calls changed</p>
        <p className="mt-0.5 text-lg font-bold text-white">{calls.total ?? 0}</p>
        <p className="text-[9px] text-slate-500">{calls.buys || 0} buy · {calls.sells || 0} trim/sell</p>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-2.5 text-center">
        <p className="flex items-center justify-center gap-1 text-[9px] uppercase tracking-wide text-slate-500"><Repeat className="h-3 w-3" />Fills</p>
        <p className="mt-0.5 text-lg font-bold text-white">{fills.total ?? 0}</p>
        <p className="text-[9px] text-slate-500">{fills.buys || 0} buy · {fills.sells || 0} sell</p>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-2.5 text-center">
        <p className="flex items-center justify-center gap-1 text-[9px] uppercase tracking-wide text-slate-500"><ShieldCheck className="h-3 w-3" />Recoveries</p>
        <p className="mt-0.5 text-lg font-bold text-emerald-300">{recoveries.total ?? 0}</p>
        <p className="text-[9px] text-slate-500">drawdowns cleared</p>
      </div>
    </div>
  );
}

function CallList({ data }) {
  const items = (data?.calls?.items) || [];
  if (items.length === 0) return null;
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
      <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">Albert&apos;s call changes</p>
      <div className="space-y-1.5">
        {items.map((c, i) => (
          <div key={i} className="flex items-center justify-between gap-2 text-[12px]">
            <span className="flex min-w-0 items-center gap-1.5"><b className="text-slate-200">{c.asset}</b><span className="truncate text-slate-400">{c.headline}</span></span>
          </div>
        ))}
      </div>
    </div>
  );
}

function FillList({ data }) {
  const items = (data?.fills?.items) || [];
  if (items.length === 0) return null;
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
      <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">Paper fills this week</p>
      <div className="space-y-1.5">
        {items.map((f, i) => (
          <div key={i} className="flex items-center justify-between gap-2 text-[12px]">
            <span className="flex items-center gap-1.5">
              {f.side === 'BUY' ? <TrendingUp className="h-3.5 w-3.5 text-emerald-400" /> : <TrendingDown className="h-3.5 w-3.5 text-rose-400" />}
              <b className="text-slate-200">{f.side} {f.asset}</b>
            </span>
            <span className={f.side === 'BUY' ? 'text-emerald-300' : 'text-rose-300'}>{fmt(f.usd)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// -------- Sunday modal (default export) --------
export default function WeeklyBrief({ onClose, onOpenCommandCentre }) {
  const { data, err } = useWeeklyBrief();
  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="max-h-[88vh] w-full max-w-md overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="relative overflow-hidden rounded-t-2xl border-b border-slate-800 bg-gradient-to-br from-violet-500/15 via-sky-500/10 to-slate-900 p-4">
          <button onClick={onClose} className="absolute right-3 top-3 text-slate-400 hover:text-white"><X className="h-4 w-4" /></button>
          <div className="flex items-center gap-3">
            <img src="/albert.png" alt="Albert" className="h-11 w-11 rounded-full ring-2 ring-violet-500/40" />
            <div>
              <p className="flex items-center gap-1 text-[11px] uppercase tracking-wide text-violet-300"><CalendarDays className="h-3 w-3" />Weekly recap{data?.weekOf ? ` · ${data.weekOf}` : ''}</p>
              <h3 className="text-lg font-bold text-white">Your week with Albert</h3>
            </div>
          </div>
        </div>

        <div className="space-y-3 p-4">
          {!data && !err && (
            <div className="flex items-center gap-2 py-10 text-[12px] text-slate-400"><Loader2 className="h-4 w-4 animate-spin" />Albert is compiling your week…</div>
          )}
          {err && <p className="py-8 text-center text-[12px] text-slate-500">Couldn&apos;t load your weekly recap right now.</p>}
          {data && (
            <>
              {data.albertLine && (
                <div className="flex items-start gap-2 rounded-xl border border-violet-500/25 bg-violet-500/[0.06] p-3">
                  <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-300" />
                  <p className="text-[13px] italic leading-relaxed text-slate-200">{data.albertLine}</p>
                </div>
              )}
              <StatTrio data={data} />
              {data.empty ? (
                <p className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-center text-[12px] text-slate-400">A calm week — no call changes, fills or drawdowns. Albert stayed patient and protected capital.</p>
              ) : (
                <>
                  <CallList data={data} />
                  <FillList data={data} />
                  {data.recoveries?.total > 0 && (
                    <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/[0.06] p-3">
                      <p className="flex items-center gap-1.5 text-[12px] font-bold text-emerald-200"><ShieldCheck className="h-3.5 w-3.5" />{data.recoveries.total} drawdown recover{data.recoveries.total === 1 ? 'y' : 'ies'} this week</p>
                      <p className="mt-0.5 text-[11px] text-slate-300">Protection engaged and then lifted — discipline held through the dip.</p>
                    </div>
                  )}
                </>
              )}
              <p className="text-center text-[10px] text-slate-600">Advisory / paper only — Albert explains, he doesn&apos;t place live trades.</p>
            </>
          )}
        </div>

        <div className="flex items-center gap-2 border-t border-slate-800 p-3">
          <button onClick={onClose} className="flex-1 rounded-xl border border-slate-700 px-3 py-2 text-[12px] font-semibold text-slate-300 hover:bg-slate-800">Dismiss</button>
          <button onClick={onOpenCommandCentre} className="flex flex-[1.4] items-center justify-center gap-1.5 rounded-xl bg-violet-500 px-3 py-2 text-[12px] font-bold text-white hover:bg-violet-400">
            Open the Command Centre<ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

// -------- Inline dashboard card --------
export function WeeklyBriefCard({ onNav }) {
  const { data, err } = useWeeklyBrief();
  const go = () => onNav && onNav('strategies');
  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-slate-800 bg-slate-950/40">
      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950/60 px-3 py-2">
        <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-300">
          <CalendarDays className="h-3.5 w-3.5 text-violet-300" />This week with Albert
        </span>
        {data?.weekOf && <span className="text-[10px] text-slate-500">{data.weekOf}</span>}
      </div>
      {!data && !err && (
        <div className="flex items-center gap-2 px-3 py-6 text-[12px] text-slate-400"><Loader2 className="h-3.5 w-3.5 animate-spin" />Compiling your week…</div>
      )}
      {data && (
        <div className="space-y-2.5 p-3">
          {data.albertLine && <p className="text-[12px] italic leading-relaxed text-slate-300">{data.albertLine}</p>}
          <StatTrio data={data} />
          {!data.empty && (
            <button onClick={go} className="flex w-full items-center justify-center gap-1 pt-0.5 text-[11px] font-semibold text-sky-400 hover:text-sky-300">
              See the full recap in the Command Centre <ArrowRight className="h-3 w-3" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
