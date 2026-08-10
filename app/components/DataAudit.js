'use client';

import React from 'react';
import { Database, Globe, Landmark, Layers, Newspaper } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from 'recharts';
import { Card } from '@/components/ui/card';
import { API_BASE } from '../lib/api';
import { fmtUsd } from '../lib/format';
import { sec } from '../lib/sections';
import { useFetch } from '../lib/useFetch';
import { SectionHead, InfoTip } from './shared';

function ConfTag({ level }) {
  const l = (level || 'LOW').toUpperCase();
  const cls = l === 'HIGH' ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
    : l === 'MEDIUM' ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
      : 'border-red-500/40 bg-red-500/10 text-red-300';
  return <span className={`rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${cls}`}>{l} confidence</span>;
}

function CompositePriceCard() {
  const [d, loading] = useFetch(`${API_BASE}/v1/composite-price`);
  const venues = (d && d.venues) || [];
  return (
    <Card className="border-0 bg-gradient-to-br from-slate-900 to-slate-950 p-6 ring-1 ring-slate-800">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Layers className="h-5 w-5 text-sky-400" />
        <h3 className="flex items-center gap-1 font-semibold text-white">BTCIQ Composite Price<InfoTip below text="A single trust-scored Bitcoin price built from the median of independent venues (Coinbase, Kraken, OKX, CoinGecko). Venues more than 0.75% from the median are flagged as outliers and excluded from the composite." /></h3>
        {d && d.confidence && <ConfTag level={d.confidence} />}
        <span className="rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300">Live · Keyless</span>
      </div>
      {loading ? <p className="text-sm text-slate-500">Polling exchange feeds…</p>
        : !d || d.status !== 'ready' ? <p className="text-sm text-slate-500">No composite price available — no live venue responded.</p>
          : (<>
            <div className="flex flex-wrap items-end gap-6">
              <div>
                <div className="text-[11px] uppercase tracking-wide text-slate-500">Composite</div>
                <div className="text-4xl font-bold text-white">{fmtUsd(d.composite)}</div>
              </div>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div><div className="text-[10px] text-slate-500">Median</div><div className="font-semibold text-slate-200">{fmtUsd(d.median)}</div></div>
                <div><div className="text-[10px] text-slate-500">Venues agree</div><div className="font-semibold text-slate-200">{d.venue_count}/4</div></div>
                <div><div className="text-[10px] text-slate-500">Spread</div><div className={`font-semibold ${(d.spread_pct || 0) < 0.5 ? 'text-emerald-400' : (d.spread_pct || 0) < 1.5 ? 'text-amber-400' : 'text-red-400'}`}>{d.spread_pct}%</div></div>
              </div>
            </div>
            <div className="mt-4 space-y-1.5">
              {venues.map((v, i) => (
                <div key={i} className={`flex items-center gap-3 rounded-lg border p-2.5 text-sm ${v.outlier ? 'border-red-500/40 bg-red-500/[0.06]' : 'border-slate-800 bg-slate-950/40'}`}>
                  <span className="flex-1 text-slate-200">{v.source}{v.outlier && <span className="ml-2 rounded border border-red-500/40 bg-red-500/10 px-1 py-0.5 text-[9px] font-bold uppercase text-red-300">outlier · excluded</span>}</span>
                  <span className="font-mono text-slate-300">{v.ok && v.price != null ? fmtUsd(v.price) : '—'}</span>
                  <span className="w-16 text-right text-[11px] text-slate-500">{v.ok && v.dev_pct != null ? '±' + v.dev_pct + '%' : (v.ok ? '' : 'no resp.')}</span>
                  <span className={`w-12 text-right text-[11px] ${v.ok ? 'text-emerald-400' : 'text-red-400'}`}>{v.ok ? (v.latency_ms != null ? v.latency_ms + 'ms' : 'ok') : 'down'}</span>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] text-slate-500">{d.method}</p>
          </>)}
    </Card>
  );
}

function CrossAssetCard() {
  const [d, loading] = useFetch(`${API_BASE}/v1/cross-asset`);
  const regimeColor = (r) => (r || '').startsWith('Risk-on') ? 'text-emerald-400' : (r || '').startsWith('Risk-off') ? 'text-amber-400' : 'text-slate-300';
  const b = (v, s) => (v == null ? '—' : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }) + (s || ''));
  return (
    <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Globe className="h-5 w-5 text-sky-400" />
        <h3 className="flex items-center gap-1 font-semibold text-white">Cross-Asset Context<InfoTip below text="Where Bitcoin sits in the broader crypto market: dominance (BTC's share of total crypto market cap), ETH/BTC ratio and total market cap. A single-aggregator read (CoinGecko)." /></h3>
        {d && d.confidence && <ConfTag level={d.confidence} />}
      </div>
      {loading ? <p className="text-sm text-slate-500">Loading market structure…</p>
        : !d || d.status !== 'ready' ? <p className="text-sm text-slate-500">No cross-asset data available.</p>
          : (<>
            <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
              <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[10px] text-slate-500">BTC dominance</div><div className="font-semibold text-white">{b(d.btc_dominance, '%')}</div></div>
              <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[10px] text-slate-500">ETH dominance</div><div className="font-semibold text-white">{b(d.eth_dominance, '%')}</div></div>
              <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[10px] text-slate-500">ETH / BTC</div><div className="font-semibold text-white">{d.eth_btc == null ? '—' : d.eth_btc}</div></div>
              <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[10px] text-slate-500">Total mcap</div><div className="font-semibold text-white">${((d.total_market_cap_usd || 0) / 1e9).toFixed(0)}B</div></div>
            </div>
            <div className="mt-3 flex items-center gap-2 text-sm">
              <span className="text-slate-500">Regime:</span>
              <span className={`font-semibold ${regimeColor(d.regime)}`}>{d.regime}</span>
              <span className="ml-auto text-[11px] text-slate-500">24h mcap {(d.mcap_change_24h >= 0 ? '+' : '') + d.mcap_change_24h}%</span>
            </div>
            <p className="mt-3 text-[11px] text-slate-400">{d.read}</p>
          </>)}
    </Card>
  );
}

function NewsToneCard() {
  const [d, loading] = useFetch(`${API_BASE}/v1/news-signals`);
  const series = (d && d.series || []).map((p) => ({ date: p.date, tone: p.tone }));
  const moodColor = (m) => m === 'Positive' ? '#34d399' : m === 'Negative' ? '#f87171' : '#94a3b8';
  return (
    <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Newspaper className="h-5 w-5 text-sky-400" />
        <h3 className="flex items-center gap-1 font-semibold text-white">News Tone (GDELT)<InfoTip below text="Global media sentiment signal for Bitcoin from GDELT's 2.0 tone timeline over 21 days. This is a media-attention SIGNAL, not a price call. Negative tone = more negative coverage." /></h3>
        {d && d.confidence && <ConfTag level={d.confidence} />}
      </div>
      {loading ? <p className="text-sm text-slate-500">Fetching global news tone…</p>
        : !d || d.status !== 'ready' ? <p className="text-sm text-slate-500">{(d && d.reason) || 'No news-tone data available.'}</p>
          : (<>
            <div className="flex items-center gap-5">
              <div><div className="text-[10px] uppercase tracking-wide text-slate-500">Latest tone</div><div className="text-3xl font-bold" style={{ color: moodColor(d.mood) }}>{d.tone_latest}</div><div className="text-xs font-semibold" style={{ color: moodColor(d.mood) }}>{d.mood}</div></div>
              <div className="text-sm text-slate-400">
                <div>21-day avg: <span className="text-slate-200">{d.tone_avg_21d}</span></div>
                <div className="mt-1">Recent 3d: <span className="text-slate-200">{d.tone_recent_3d}</span></div>
                <div className="mt-1">Direction: <span className="text-slate-200">{d.direction}</span></div>
              </div>
            </div>
            <div className="mt-3 h-20 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={series} margin={{ top: 2, right: 4, left: -28, bottom: 0 }}>
                  <YAxis hide domain={['auto', 'auto']} /><XAxis dataKey="date" hide />
                  <ReferenceLine y={0} stroke="#334155" strokeDasharray="3 3" />
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }} labelFormatter={() => ''} formatter={(v) => [v, 'Tone']} />
                  <Line type="monotone" dataKey="tone" stroke="#38bdf8" strokeWidth={1.6} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-[11px] text-slate-400">{d.read}</p>
          </>)}
    </Card>
  );
}

function MacroFredCard() {
  const [d, loading] = useFetch(`${API_BASE}/v1/macro-fred`);
  const rows = (d && d.series) || [];
  return (
    <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Landmark className="h-5 w-5 text-sky-400" />
        <h3 className="flex items-center gap-1 font-semibold text-white">US Macro (FRED)<InfoTip below text="Key US macro readings from the St. Louis Fed (FRED): policy rate, Treasury yields, the 2s10s spread, CPI, M2 money supply and unemployment. Loose money conditions tend to support Bitcoin." /></h3>
        {d && d.status === 'ready' && <ConfTag level={d.confidence} />}
        {d && d.status === 'ready' && <span className="rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300">Live</span>}
      </div>
      {loading ? <p className="text-sm text-slate-500">Loading macro series…</p>
        : !d || d.status !== 'ready' ? <p className="text-sm text-slate-500">{(d && d.reason) || 'No FRED data available.'}</p>
          : (<>
            <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
              {rows.map((r, i) => (
                <div key={i} className="rounded border border-slate-800 bg-slate-950/40 p-2.5">
                  <div className="text-[10px] text-slate-500">{r.label}</div>
                  <div className="font-semibold text-white">{Number(r.value).toLocaleString(undefined, { maximumFractionDigits: 2 })}</div>
                  <div className={`text-[10px] ${r.change == null ? 'text-slate-600' : r.change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{r.change == null ? r.date : (r.change >= 0 ? '+' : '') + r.change}</div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] text-slate-500">{d.note} · Source: {d.source}</p>
          </>)}
    </Card>
  );
}

function DataAuditSection() {
  return (
    <div className="space-y-5">
      <SectionHead icon={Database} title="Data Audit" blurb={sec('dataaudit').blurb} coin="BTC" />
      <CompositePriceCard />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CrossAssetCard />
        <NewsToneCard />
      </div>
      <MacroFredCard />
    </div>
  );
}



export default DataAuditSection;
