'use client';

import React from 'react';
import { API_BASE } from '../lib/api';
import { Check, Loader2, TrendingUp, TrendingDown } from 'lucide-react';

// Compact, save-able multi-coin basket draft rendered inside an Albert chat reply
// ("Basket from Chat"). Tapping "Save & track" activates it for the signed-in user.
export default function BasketChatCard({ draft, pid }) {
  const [saving, setSaving] = React.useState(false);
  const [saved, setSaved] = React.useState(false);
  const [error, setError] = React.useState('');
  const legs = (draft && draft.legs) || [];
  if (!legs.length) return null;

  const save = async () => {
    if (saving || saved) return;
    setSaving(true);
    setError('');
    try {
      const r = await fetch(`${API_BASE}/v1/albert/strategy/basket`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft, pid }),
      });
      const j = await r.json();
      if (j && j.status === 'ready') setSaved(true);
      else setError((j && j.message) || 'Could not save the basket.');
    } catch (e) {
      setError('Network error — please try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-slate-700 bg-slate-950/70 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="truncate text-[13px] font-semibold text-slate-100">{draft.title || 'Multi-Coin Strategy'}</p>
        <span className="shrink-0 rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400">
          {legs.length} legs · {draft.horizon_days || 30}d
        </span>
      </div>
      <div className="space-y-1">
        {legs.map((l, i) => {
          const long = (l.position || 'long') === 'long';
          return (
            <div key={i} className="flex items-center justify-between rounded-lg bg-slate-900/60 px-2.5 py-1.5 text-[12px]">
              <span className="flex items-center gap-1.5 font-medium text-slate-200">
                {long ? <TrendingUp className="h-3.5 w-3.5 text-emerald-400" /> : <TrendingDown className="h-3.5 w-3.5 text-rose-400" />}
                {l.symbol}
                <span className={long ? 'text-emerald-400' : 'text-rose-400'}>{long ? 'Long' : 'Short'}</span>
              </span>
              <span className="text-slate-400">{Math.round(l.weight_pct || 0)}%</span>
            </div>
          );
        })}
      </div>
      {error && <p className="mt-2 text-[11px] text-rose-400">{error}</p>}
      <button
        onClick={save}
        disabled={saving || saved}
        className={`mt-2.5 flex w-full items-center justify-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-semibold transition-colors disabled:opacity-70 ${
          saved
            ? 'border border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
            : 'bg-gradient-to-r from-sky-500 to-violet-600 text-white hover:opacity-90'
        }`}
      >
        {saved ? (<><Check className="h-3.5 w-3.5" />Saved &amp; tracking — see Trading Strategies</>)
          : saving ? (<><Loader2 className="h-3.5 w-3.5 animate-spin" />Saving…</>)
          : 'Save & track'}
      </button>
    </div>
  );
}
