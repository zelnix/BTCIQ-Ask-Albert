'use client';

import React from 'react';
import { Briefcase, Plus, Trash2, Save, Check } from 'lucide-react';
import { API_BASE, getPid } from '../lib/api';

const COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'LINK', 'MATIC'];

export default function PortfolioPanel({ onSaved }) {
  const [rows, setRows] = React.useState([]);
  const [saved, setSaved] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const pid = React.useMemo(() => getPid(), []);

  React.useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API_BASE}/v1/portfolio?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' });
        const j = await r.json();
        setRows((j.positions && j.positions.length) ? j.positions : [{ asset: 'BTC', size: '', avg_entry: '' }]);
      } catch (e) {
        setRows([{ asset: 'BTC', size: '', avg_entry: '' }]);
      } finally { setLoading(false); }
    })();
  }, [pid]);

  const update = (i, key, val) => { setSaved(false); setRows((r) => r.map((row, idx) => (idx === i ? { ...row, [key]: val } : row))); };
  const addRow = () => setRows((r) => [...r, { asset: 'ETH', size: '', avg_entry: '' }]);
  const removeRow = (i) => setRows((r) => r.filter((_, idx) => idx !== i));

  const save = async () => {
    const positions = rows
      .filter((r) => r.asset)
      .map((r) => ({ asset: r.asset, size: r.size === '' ? null : Number(r.size), avg_entry: r.avg_entry === '' ? null : Number(r.avg_entry) }));
    try {
      await fetch(`${API_BASE}/v1/portfolio`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid, positions }),
      });
      setSaved(true);
      if (onSaved) onSaved(positions);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) { /* noop */ }
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Briefcase className="h-4 w-4 text-sky-400" />
        <h3 className="text-sm font-semibold text-white">My Position</h3>
        <span className="text-[10px] text-slate-500">Albert tailors buy/sell calls to this</span>
      </div>
      {loading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : (
        <div className="space-y-2">
          {rows.map((row, i) => (
            <div key={i} className="flex items-center gap-2">
              <select value={row.asset} onChange={(e) => update(i, 'asset', e.target.value)}
                className="w-20 rounded-md border border-slate-700 bg-slate-950/60 px-2 py-1.5 text-xs text-slate-100 focus:border-sky-500/50 focus:outline-none">
                {COINS.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <input type="number" step="any" value={row.size ?? ''} onChange={(e) => update(i, 'size', e.target.value)} placeholder="Size (e.g. 0.5)"
                className="w-28 rounded-md border border-slate-700 bg-slate-950/60 px-2 py-1.5 text-xs text-slate-100 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none" />
              <input type="number" step="any" value={row.avg_entry ?? ''} onChange={(e) => update(i, 'avg_entry', e.target.value)} placeholder="Avg entry $"
                className="w-28 rounded-md border border-slate-700 bg-slate-950/60 px-2 py-1.5 text-xs text-slate-100 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none" />
              <button onClick={() => removeRow(i)} className="rounded-md p-1.5 text-slate-500 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
          ))}
          <div className="flex items-center gap-2 pt-1">
            <button onClick={addRow} className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:text-white"><Plus className="h-3 w-3" />Add</button>
            <button onClick={save} className={`inline-flex items-center gap-1 rounded-md px-3 py-1 text-xs font-semibold ${saved ? 'bg-emerald-500/20 text-emerald-300' : 'bg-sky-500 text-white hover:bg-sky-400'}`}>
              {saved ? <><Check className="h-3 w-3" />Saved</> : <><Save className="h-3 w-3" />Save</>}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
