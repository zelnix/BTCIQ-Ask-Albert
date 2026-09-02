'use client';

import React from 'react';
import { BellRing, X, CheckCircle2 } from 'lucide-react';
import { API_BASE, getPid } from '../lib/api';

export default function AlertManager() {
  const [active, setActive] = React.useState([]);
  const [triggered, setTriggered] = React.useState([]);
  const pid = React.useMemo(() => getPid(), []);

  const load = React.useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/v1/price-alerts?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' });
      const j = await r.json();
      setActive(j.watches || []);
      setTriggered(j.triggered || []);
    } catch (e) { /* noop */ }
  }, [pid]);

  React.useEffect(() => {
    load();
    const id = setInterval(load, 20000);
    const onCreated = () => load();
    window.addEventListener('btciq:alert-created', onCreated);
    return () => { clearInterval(id); window.removeEventListener('btciq:alert-created', onCreated); };
  }, [load]);

  const cancel = async (id) => {
    setActive((a) => a.filter((w) => w.id !== id));
    try { await fetch(`${API_BASE}/v1/price-alert/${id}`, { method: 'DELETE' }); } catch (e) { /* noop */ }
    load();
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <div className="mb-3 flex items-center gap-2">
        <BellRing className="h-4 w-4 text-amber-400" />
        <h3 className="text-sm font-semibold text-white">Price Alerts</h3>
        <span className="text-[10px] text-slate-500">levels you set from Albert</span>
      </div>
      {active.length === 0 && triggered.length === 0 ? (
        <p className="text-xs text-slate-500">No price alerts yet. In any Albert answer, tap an &ldquo;Alert @ $X&rdquo; chip to get pinged when price crosses that level.</p>
      ) : (
        <div className="space-y-1.5">
          {active.map((w) => (
            <div key={w.id} className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-2.5 py-1.5 text-xs">
              <span className="font-semibold text-slate-200">{w.asset}</span>
              <span className="text-slate-400">crosses {w.direction} <span className="font-semibold text-sky-300">${Number(w.level).toLocaleString()}</span></span>
              <button onClick={() => cancel(w.id)} className="ml-auto rounded-md p-1 text-slate-500 hover:text-red-400" title="Cancel alert"><X className="h-3.5 w-3.5" /></button>
            </div>
          ))}
          {triggered.map((w) => (
            <div key={w.id} className="flex items-center gap-2 rounded-lg border border-emerald-800/40 bg-emerald-950/20 px-2.5 py-1.5 text-xs opacity-80">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
              <span className="font-semibold text-slate-300">{w.asset}</span>
              <span className="text-slate-500">hit ${Number(w.level).toLocaleString()}</span>
              <span className="ml-auto text-[10px] font-semibold text-emerald-400">triggered</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
