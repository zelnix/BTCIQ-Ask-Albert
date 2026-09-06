'use client';

import React from 'react';
import { API_BASE } from '../lib/api';
import { Check, Loader2, XCircle } from 'lucide-react';

// Inline "Chat Basket Close" confirmation: Albert asks to confirm before closing a basket.
export default function BasketCloseCard({ close }) {
  const [state, setState] = React.useState('idle'); // idle | closing | done | error
  if (!close || !close.basket_id) return null;
  const pnl = close.total_pnl_pct;
  const pnlColor = pnl == null ? 'text-slate-400' : pnl >= 0 ? 'text-emerald-400' : 'text-rose-400';

  const doClose = async () => {
    if (state === 'closing' || state === 'done') return;
    setState('closing');
    try {
      const r = await fetch(`${API_BASE}/v1/albert/strategy/basket/${close.basket_id}/close`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const j = await r.json();
      setState(j && j.status === 'ready' ? 'done' : 'error');
    } catch (e) {
      setState('error');
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-rose-500/30 bg-rose-500/[0.06] p-3">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="truncate text-[12px] font-semibold text-slate-100">{close.title || 'Basket'}</span>
        {pnl != null && <span className={`shrink-0 text-[11px] font-semibold ${pnlColor}`}>{pnl >= 0 ? '+' : ''}{pnl}%</span>}
      </div>
      {state === 'done' ? (
        <p className="flex items-center gap-1.5 text-[12px] font-semibold text-emerald-300"><Check className="h-3.5 w-3.5" />Closed — moved to past baskets</p>
      ) : (
        <button
          onClick={doClose}
          disabled={state === 'closing'}
          className="flex w-full items-center justify-center gap-1.5 rounded-full bg-rose-600 px-3 py-1.5 text-[12px] font-semibold text-white transition-colors hover:bg-rose-500 disabled:opacity-70"
        >
          {state === 'closing' ? (<><Loader2 className="h-3.5 w-3.5 animate-spin" />Closing…</>)
            : state === 'error' ? (<><XCircle className="h-3.5 w-3.5" />Failed — tap to retry</>)
            : (<><XCircle className="h-3.5 w-3.5" />Close basket</>)}
        </button>
      )}
    </div>
  );
}
