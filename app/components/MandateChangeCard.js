'use client';
// Mandate-change card rendered inside Ask-Albert chat when the user asks to
// change their risk/mandate settings. Albert proposes; the user taps Apply
// (POST /api/v1/albert/mandate with the full proposed mandate) or Cancel.
// Albert never auto-applies changes to trading inputs.
import React from 'react';
import { API_BASE } from '../lib/api';
import { SlidersHorizontal, Check, X, Loader2, ArrowRight } from 'lucide-react';

export default function MandateChangeCard({ change, pid }) {
  const [state, setState] = React.useState('proposed'); // proposed | applying | applied | cancelled | error
  const changes = (change && change.changes) || [];
  if (!change || !changes.length) return null;

  const apply = async () => {
    if (!pid) { setState('error'); return; }
    setState('applying');
    try {
      const r = await fetch(`${API_BASE}/v1/albert/mandate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid, mandate: change.proposed }),
      });
      const j = await r.json();
      setState(j && j.mandate ? 'applied' : 'error');
    } catch (e) { setState('error'); }
  };

  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-violet-500/30 bg-violet-500/[0.06]">
      <div className="flex items-center gap-1.5 border-b border-violet-500/20 px-3 py-2">
        <SlidersHorizontal className="h-3.5 w-3.5 text-violet-300" />
        <span className="text-[11px] font-bold uppercase tracking-wider text-violet-200">Proposed mandate change</span>
      </div>
      <div className="space-y-1.5 p-3">
        {changes.map((c, i) => (
          <div key={i} className="flex items-center justify-between gap-2 text-[12px]">
            <span className="shrink-0 text-slate-400">{c.label}</span>
            <span className="flex min-w-0 items-center gap-1.5 text-right">
              <span className="truncate text-slate-500 line-through decoration-slate-600">{c.from}</span>
              <ArrowRight className="h-3 w-3 shrink-0 text-violet-300" />
              <span className="truncate font-semibold text-slate-100">{c.to}</span>
            </span>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2 border-t border-violet-500/20 px-3 py-2">
        {state === 'applied' ? (
          <span className="flex items-center gap-1.5 text-[12px] font-semibold text-emerald-300"><Check className="h-4 w-4" />Mandate updated</span>
        ) : state === 'cancelled' ? (
          <span className="text-[12px] text-slate-500">Left unchanged.</span>
        ) : (
          <>
            <button onClick={apply} disabled={state === 'applying'}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-violet-500 px-3 py-1.5 text-[12px] font-bold text-white transition-colors hover:bg-violet-400 disabled:opacity-60">
              {state === 'applying' ? <><Loader2 className="h-3.5 w-3.5 animate-spin" />Applying…</> : <><Check className="h-3.5 w-3.5" />Apply</>}
            </button>
            <button onClick={() => setState('cancelled')} disabled={state === 'applying'}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-[12px] font-semibold text-slate-300 hover:bg-slate-800">
              <X className="h-3.5 w-3.5" />Cancel
            </button>
          </>
        )}
        {state === 'error' && <span className="text-[11px] text-rose-400">Couldn’t apply — try again.</span>}
      </div>
    </div>
  );
}
