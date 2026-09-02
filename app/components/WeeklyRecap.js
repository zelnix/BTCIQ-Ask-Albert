'use client';

import React from 'react';
import { CalendarDays, RefreshCw } from 'lucide-react';
import { API_BASE } from '../lib/api';
import AlbertText from './AlbertText';

export default function WeeklyRecap() {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(async (refresh) => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/v1/albert/weekly-recap${refresh ? '?refresh=true' : ''}`, { cache: 'no-store' });
      const j = await r.json();
      setData(j);
    } catch (e) { /* noop */ } finally { setLoading(false); }
  }, []);

  React.useEffect(() => { load(false); }, [load]);

  const text = data && data.text;
  const when = data && data.created_at;

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
    </div>
  );
}
