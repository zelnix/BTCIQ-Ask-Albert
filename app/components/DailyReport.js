'use client';

import React from 'react';
import { Button } from '@/components/ui/button';
import { API_BASE } from '../lib/api';
import { fmtUsd } from '../lib/format';
import { useFetch } from '../lib/useFetch';

// Shareable Daily Report — a clean, exportable (PNG) snapshot of the day's key numbers.
export default function DailyReportModal({ d, onClose }) {
  const cardRef = React.useRef(null);
  const [exporting, setExporting] = React.useState(false);
  const [cp] = useFetch(`${API_BASE}/v1/composite-price`);
  const [fred] = useFetch(`${API_BASE}/v1/macro-fred`);
  const [xa] = useFetch(`${API_BASE}/v1/cross-asset`);
  const [ns] = useFetch(`${API_BASE}/v1/news-signals`);

  const today = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
  const dec = (d && d.decision) || {};
  const score = d && d.quant_score;
  const scoreLabel = d && d.quant_label;
  const price = (cp && cp.composite) || (d && d.last_close);
  const conf = cp && cp.confidence;
  const macroBy = {};
  ((fred && fred.series) || []).forEach((r) => { macroBy[r.id] = r; });
  const macroRows = [macroBy['DFF'], macroBy['DGS10'], macroBy['CPIAUCSL'], macroBy['UNRATE']].filter(Boolean);
  const sc = (v) => v == null ? '#94a3b8' : v >= 60 ? '#34d399' : v >= 55 ? '#a3e635' : v > 45 ? '#fbbf24' : v > 40 ? '#fb923c' : '#f87171';

  const exportPng = async () => {
    if (!cardRef.current) return;
    setExporting(true);
    try {
      const html2canvas = (await import('html2canvas')).default;
      const canvas = await html2canvas(cardRef.current, { backgroundColor: '#0b1220', scale: 2, useCORS: true, logging: false });
      const link = document.createElement('a');
      link.download = `BTCIQ-report-${new Date().toISOString().slice(0, 10)}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    } catch (e) { /* noop */ } finally { setExporting(false); }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="max-h-[92vh] w-full max-w-md overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        {/* Exportable card */}
        <div ref={cardRef} className="rounded-2xl border border-slate-700 bg-[#0b1220] p-6" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-amber-400 to-orange-500 text-sm font-black text-black">₿</span>
              <div>
                <div className="text-base font-black tracking-tight text-white">BTCIQ</div>
                <div className="text-[10px] text-slate-500">Daily Bitcoin Snapshot</div>
              </div>
            </div>
            <div className="text-right text-[10px] text-slate-400">{today}</div>
          </div>

          <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-end justify-between">
              <div>
                <div className="text-[10px] uppercase tracking-wide text-slate-500">Composite Price</div>
                <div className="text-3xl font-bold text-white">{price != null ? fmtUsd(price) : '—'}</div>
              </div>
              {conf && <span className={`rounded border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${conf === 'HIGH' ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : conf === 'MEDIUM' ? 'border-amber-500/40 bg-amber-500/10 text-amber-300' : 'border-red-500/40 bg-red-500/10 text-red-300'}`}>{conf} confidence</span>}
            </div>
          </div>

          <div className="mb-4 grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-center">
              <div className="text-[10px] uppercase tracking-wide text-slate-500">Quant Score</div>
              <div className="text-2xl font-bold" style={{ color: sc(score) }}>{score != null ? score : '—'}</div>
              <div className="text-[10px] font-semibold" style={{ color: sc(score) }}>{scoreLabel || ''}</div>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-center">
              <div className="text-[10px] uppercase tracking-wide text-slate-500">Market State</div>
              <div className="text-2xl font-bold" style={{ color: sc(dec.overall_score) }}>{dec.overall_score != null ? dec.overall_score : '—'}</div>
              <div className="text-[10px] font-semibold text-slate-300">{dec.label || ''}</div>
            </div>
          </div>

          <div className="mb-4 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-2.5">
              <div className="text-[9px] uppercase text-slate-500">Risk</div>
              <div className="text-sm font-bold text-white">{dec.risk_level || '—'}</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-2.5">
              <div className="text-[9px] uppercase text-slate-500">BTC Dom.</div>
              <div className="text-sm font-bold text-white">{xa && xa.btc_dominance != null ? xa.btc_dominance + '%' : '—'}</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-2.5">
              <div className="text-[9px] uppercase text-slate-500">News Tone</div>
              <div className="text-sm font-bold" style={{ color: ns && ns.mood === 'Positive' ? '#34d399' : ns && ns.mood === 'Negative' ? '#f87171' : '#cbd5e1' }}>{ns && ns.status === 'ready' ? ns.mood : '—'}</div>
            </div>
          </div>

          {macroRows.length > 0 && (
            <div className="mb-3">
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">US Macro (FRED)</div>
              <div className="grid grid-cols-2 gap-2">
                {macroRows.map((r, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 px-2.5 py-1.5">
                    <span className="text-[11px] text-slate-400">{r.label}</span>
                    <span className="text-[12px] font-semibold text-white">{Number(r.value).toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {dec.regime && <div className="rounded-lg border border-sky-500/20 bg-sky-500/[0.06] p-2.5 text-[11px] text-slate-300"><span className="font-semibold text-sky-300">Regime:</span> {dec.regime}</div>}

          <div className="mt-4 border-t border-slate-800 pt-2 text-center text-[9px] text-slate-600">
            Generated by BTCIQ · powered by BitCentAI · Educational only — not financial advice
          </div>
        </div>

        {/* Controls */}
        <div className="mt-3 flex items-center justify-center gap-2">
          <Button onClick={exportPng} disabled={exporting} className="gap-2 bg-gradient-to-r from-sky-500 to-violet-600 text-white hover:from-sky-400 hover:to-violet-500">
            {exporting ? 'Rendering…' : 'Download PNG'}
          </Button>
          <Button onClick={onClose} variant="outline" className="border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800">Close</Button>
        </div>
      </div>
    </div>
  );
}
