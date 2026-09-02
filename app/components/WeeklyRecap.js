'use client';

import React from 'react';
import { CalendarDays, RefreshCw, History, ChevronDown } from 'lucide-react';
import { API_BASE } from '../lib/api';
import AlbertText from './AlbertText';

export default function WeeklyRecap() {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [history, setHistory] = React.useState([]);
  const [showHistory, setShowHistory] = React.useState(false);
  const [openId, setOpenId] = React.useState(null);

  const loadHistory = React.useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/v1/albert/weekly-recap/history`, { cache: 'no-store' });
      const j = await r.json();
      setHistory((j && j.recaps) || []);
    } catch (e) { /* noop */ }
  }, []);

  const load = React.useCallback(async (refresh) => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/v1/albert/weekly-recap${refresh ? '?refresh=true' : ''}`, { cache: 'no-store' });
      const j = await r.json();
      setData(j);
    } catch (e) { /* noop */ } finally { setLoading(false); loadHistory(); }
  }, [loadHistory]);

  React.useEffect(() => { load(false); }, [load]);

  const text = data && data.text;
  const when = data && data.created_at;
  // Past recaps = everything in history except the current/most-recent one.
  const past = history.filter((h) => h.created_at !== when).slice(0, history.length);

  return (
    <div className="rounded-xl border border-slate-800 bg-gradient-to-br from-violet-950/30 to-slate-900/50 p-4">
      <div className="mb-3 flex items-center gap-2">
        <CalendarDays className="h-4 w-4 text-violet-400" />
        <h3 className="text-sm font-semibold text-white">Albert&apos;s Weekly Recap</h3>
        {when && <span className="text-[10px] text-slate-500">{new Date(when).toLocaleDateString()}</span>}
        <button onClick={() => load(true)} disabled={loading} title="Regenerate"
          className="ml-auto rounded-md p-1 text-slate-400 transition-colors hover:text-white disabled:opacity-50">
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
      {loading && !text ? (
        <p className="text-xs text-slate-500">Albert is reviewing the week…</p>
      ) : text ? (
        <div className="text-[13px] leading-relaxed text-slate-200"><AlbertText text={text} /></div>
      ) : (
        <p className="text-xs text-slate-500">Weekly recap will appear once Albert has logged some calls. Ask him a buy/sell question to get started.</p>
      )}

      {past.length > 0 && (
        <div className="mt-4 border-t border-slate-800 pt-3">
          <button onClick={() => setShowHistory((v) => !v)}
            className="flex w-full items-center gap-1.5 text-[11px] font-semibold text-slate-400 transition-colors hover:text-slate-200">
            <History className="h-3.5 w-3.5 text-violet-400" />
            Past recaps ({past.length})
            <ChevronDown className={`ml-auto h-3.5 w-3.5 transition-transform ${showHistory ? 'rotate-180' : ''}`} />
          </button>
          {showHistory && (
            <div className="mt-2 max-h-72 space-y-1.5 overflow-y-auto pr-1">
              {past.map((h) => {
                const id = h.week_label || h.created_at;
                const isOpen = openId === id;
                const hr = h.stats && h.stats.hit_rate;
                return (
                  <div key={id} className="rounded-lg border border-slate-800 bg-slate-950/40">
                    <button onClick={() => setOpenId(isOpen ? null : id)}
                      className="flex w-full items-center gap-2 px-2.5 py-2 text-left">
                      <span className="text-[12px] font-semibold text-slate-200">{h.week_label || new Date(h.created_at).toLocaleDateString()}</span>
                      {hr != null && (
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${hr >= 50 ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'}`}>{hr}% hit</span>
                      )}
                      <span className="text-[10px] text-slate-500">{new Date(h.created_at).toLocaleDateString()}</span>
                      <ChevronDown className={`ml-auto h-3.5 w-3.5 text-slate-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                    </button>
                    {isOpen && (
                      <div className="border-t border-slate-800 px-2.5 py-2 text-[12px] leading-relaxed text-slate-300">
                        <AlbertText text={h.text} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
