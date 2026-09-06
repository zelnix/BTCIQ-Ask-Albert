'use client';

import React from 'react';
import { API_BASE } from '../lib/api';
import { Check, Loader2, ArrowRight, Scale } from 'lucide-react';

// Inline "Chat Rebalance" suggestion: Albert proposes new weights for one of the user's
// saved baskets and this card lets them apply them without leaving the chat.
export default function BasketRebalanceCard({ rebalance }) {
  const [applying, setApplying] = React.useState(false);
  const [applied, setApplied] = React.useState(false);
  const [error, setError] = React.useState('');
  const legs = (rebalance && rebalance.legs) || [];
  if (!legs.length) return null;

  const apply = async () => {
    if (applying || applied) return;
    setApplying(true);
    setError('');
    try {
      const weights = {};
      legs.forEach((l) => { weights[l.symbol] = l.suggested_weight; });
      const r = await fetch(`${API_BASE}/v1/albert/strategy/basket/${rebalance.basket_id}/reweight`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ weights }),
      });
      const j = await r.json();
      if (j && j.status === 'ready') setApplied(true);
      else setError((j && j.message) || 'Could not apply weights.');
    } catch (e) {
      setError('Network error — please try again.');
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-violet-500/30 bg-violet-500/[0.06] p-3">
      <div className="mb-1.5 flex items-center gap-1.5 text-[12px] font-semibold text-violet-300">
        <Scale className="h-3.5 w-3.5" />{rebalance.title || 'Strategy rebalance'}
      </div>
      <div className="space-y-1">
        {legs.map((l) => {
          const diff = (l.suggested_weight || 0) - (l.current_weight || 0);
          return (
            <div key={l.symbol} className="flex items-center justify-between text-[11px]">
              <span className="font-semibold text-slate-200">{l.symbol}</span>
              <span className="text-slate-400">
                {Math.round(l.current_weight)}% <ArrowRight className="inline h-3 w-3 text-slate-600" />{' '}
                <span className="font-semibold text-slate-100">{Math.round(l.suggested_weight)}%</span>{' '}
                <span className={diff >= 0 ? 'text-emerald-400' : 'text-rose-400'}>({diff >= 0 ? '+' : ''}{Math.round(diff)})</span>
              </span>
            </div>
          );
        })}
      </div>
      {error && <p className="mt-2 text-[11px] text-rose-400">{error}</p>}
      <button
        onClick={apply}
        disabled={applying || applied}
        className={`mt-2.5 flex w-full items-center justify-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-semibold transition-colors disabled:opacity-70 ${
          applied ? 'border border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'bg-violet-600 text-white hover:bg-violet-500'
        }`}
      >
        {applied ? (<><Check className="h-3.5 w-3.5" />Weights applied — see Trading Strategies</>)
          : applying ? (<><Loader2 className="h-3.5 w-3.5 animate-spin" />Applying…</>)
          : 'Apply weights'}
      </button>
    </div>
  );
}
