'use client';

import React from 'react';
import { Activity, ArrowDownRight, ArrowUpRight, ChevronDown, Fish, Landmark, Waves } from 'lucide-react';
import { ResponsiveContainer, ComposedChart, Line, LineChart, Area, Bar, BarChart, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, Cell } from 'recharts';
import { Card } from '@/components/ui/card';
import { API_BASE } from '../lib/api';
import { sigColor, sigHex, shortDate } from '../lib/format';
import { sec } from '../lib/sections';
import { SectionHead, AiReview, InfoTip, CoinIcon, Spark } from './shared';
import { useFetch } from '../lib/useFetch';

function ExchangeNetFlowCard() {
  const [d, loading] = useFetch(`${API_BASE}/v1/exchange-flows`);
  const series = (d && d.series || []).map((x) => ({ date: x.date, bal: x.balance }));
  const fChg = (v) => v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }) + ' BTC';
  const trendColor = (t) => (t || '').startsWith('Outflow') ? 'text-emerald-400' : (t || '').startsWith('Inflow') ? 'text-red-400' : 'text-slate-300';
  return (
    <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <ArrowUpRight className="h-5 w-5 text-sky-400" />
        <h3 className="flex items-center gap-1 font-semibold text-white">Exchange Net-Flow<InfoTip below text="Total BTC held by tracked exchange wallets over time. Coins leaving exchanges (outflow) reduce immediately sellable supply and read bullish; inflows read bearish." /></h3>
        <span className="rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300">Live</span>
      </div>
      {loading ? <p className="text-sm text-slate-500">Reconstructing exchange balances from on-chain history…</p> : !series.length ? <p className="text-sm text-slate-500">No exchange-flow data available.</p> : (<>
        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[10px] text-slate-500">Held now</div><div className="font-semibold text-white">{Number(d.current).toLocaleString(undefined, { maximumFractionDigits: 0 })} BTC</div></div>
          <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[10px] text-slate-500">7d</div><div className={`font-semibold ${(d.net_7d || 0) <= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{fChg(d.net_7d)}</div></div>
          <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[10px] text-slate-500">30d</div><div className={`font-semibold ${(d.net_30d || 0) <= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{fChg(d.net_30d)}</div></div>
          <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[10px] text-slate-500">Trend</div><div className={`text-xs font-semibold ${trendColor(d.trend)}`}>{d.trend}</div></div>
        </div>
        <div className="h-32 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series} margin={{ top: 4, right: 6, left: 6, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#64748b' }} tickLine={false} axisLine={{ stroke: '#1e293b' }} minTickGap={40} tickFormatter={shortDate} />
              <YAxis tick={{ fontSize: 9, fill: '#64748b' }} tickLine={false} axisLine={false} width={52} domain={['auto', 'auto']} tickFormatter={(v) => (v / 1000).toFixed(0) + 'k'} />
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }} labelFormatter={shortDate} formatter={(v) => [Number(v).toLocaleString() + ' BTC', 'Exchange balance']} />
              <Line type="monotone" dataKey="bal" stroke="#38bdf8" strokeWidth={1.6} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-[11px] text-slate-400">{d.read}</p>
      </>)}
    </Card>
  );
}

const fMln = (v) => (v == null ? '—' : (v >= 0 ? '+$' : '-$') + Math.abs(Number(v)).toLocaleString(undefined, { maximumFractionDigits: 0 }) + 'M');

function EtfFlowsCard() {
  const [d, setD] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/v1/etf-flows`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => { if (alive) { setD(j); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  const daily = (d && d.daily) || [];
  const bars = daily.slice(0, 30).reverse().map((x) => ({ date: shortDate(x.date), total: x.total }));
  const cum = (d && d.cumulative) || [];
  const lead = (d && d.leaderboard) || [];
  const maxLead = Math.max(1, ...lead.map((l) => Math.abs(l.window_total || 0)));
  const netColor = (v) => (v == null ? 'text-slate-300' : v >= 0 ? 'text-emerald-400' : 'text-red-400');
  return (
    <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Landmark className="h-5 w-5 text-sky-400" />
        <h3 className="flex items-center gap-1 font-semibold text-white">US Spot Bitcoin ETF Flows<InfoTip below text="Daily net creations/redemptions across US spot Bitcoin ETFs, in USD millions. Sustained net inflows mean funds are buying BTC to back new shares (demand); net outflows mean the opposite." /></h3>
        <span className="rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300">Live</span>
        <span className="ml-auto text-[11px] text-slate-500">{d && d.source}</span>
      </div>
      {loading ? (
        <p className="text-sm text-slate-500">Loading ETF flow data…</p>
      ) : !daily.length ? (
        <p className="text-sm text-slate-500">ETF flow data is refreshing — check back in a moment.</p>
      ) : (
        <>
          <div className="mb-4 grid grid-cols-3 gap-3">
            {[['Net flow (1d)', d.net_1d], ['Net flow (7d)', d.net_7d], ['Net flow (window)', d.net_30d]].map(([lab, v], i) => (
              <div key={i} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                <div className="text-[11px] text-slate-500">{lab}</div>
                <div className={`text-lg font-semibold ${netColor(v)}`}>{fMln(v)}</div>
              </div>
            ))}
          </div>
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Daily net flow ($M){d.latest_date ? ` · latest ${shortDate(d.latest_date)}` : ''}</div>
          <div className="h-40 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={bars} margin={{ top: 5, right: 5, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#64748b' }} tickLine={false} axisLine={{ stroke: '#1e293b' }} />
                <YAxis tick={{ fontSize: 10, fill: '#64748b' }} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} formatter={(v) => [fMln(v), 'Net flow']} />
                <ReferenceLine y={0} stroke="#475569" />
                <Bar dataKey="total" radius={[3, 3, 0, 0]}>
                  {bars.map((b, i) => <Cell key={i} fill={b.total >= 0 ? '#34d399' : '#f87171'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {cum.length > 1 && (
            <>
              <div className="mt-4 mb-2 flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Cumulative net flow vs BTC price
                {d.cum_total != null && <span className={`normal-case ${netColor(d.cum_total)}`}>· total {fMln(d.cum_total)}</span>}
                {d.history_days ? <span className="ml-auto normal-case text-slate-600">{d.history_days} days{d.span_from ? ` · from ${shortDate(d.span_from)}` : ''}</span> : null}
              </div>
              <div className="h-44 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={cum} margin={{ top: 5, right: 4, left: -6, bottom: 0 }}>
                    <defs>
                      <linearGradient id="etfCum" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#64748b' }} tickLine={false} axisLine={{ stroke: '#1e293b' }} minTickGap={40} tickFormatter={shortDate} />
                    <YAxis yAxisId="cum" tick={{ fontSize: 9, fill: '#64748b' }} tickLine={false} axisLine={false} width={52} tickFormatter={(v) => (Math.abs(v) >= 1000 ? (v / 1000).toFixed(0) + 'B' : v)} />
                    <YAxis yAxisId="px" orientation="right" hide domain={['auto', 'auto']} />
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} labelFormatter={shortDate} formatter={(v, n) => [n === 'price' ? '$' + Number(v).toLocaleString() : fMln(v), n === 'price' ? 'BTC price' : 'Cumulative flow']} />
                    <Area yAxisId="cum" type="monotone" dataKey="cum" stroke="#38bdf8" strokeWidth={1.8} fill="url(#etfCum)" dot={false} />
                    {d.has_price && <Line yAxisId="px" type="monotone" dataKey="price" stroke="#f59e0b" strokeWidth={1.5} dot={false} />}
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              {d.has_price && <div className="mt-1 flex gap-4 text-[10px] text-slate-500"><span className="flex items-center gap-1"><span className="inline-block h-2 w-3 rounded-sm bg-sky-400/60" />Cumulative ETF flow</span><span className="flex items-center gap-1"><span className="inline-block h-0.5 w-3 bg-amber-500" />BTC price</span></div>}
            </>
          )}
          <div className="mt-4 mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">By issuer (last 30 days)</div>
          <div className="space-y-1.5">
            {lead.slice(0, 8).map((l, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="w-14 font-mono font-semibold text-slate-200">{l.ticker}</span>
                <div className="relative h-3 flex-1 overflow-hidden rounded bg-slate-800/50">
                  <div className={`absolute top-0 h-3 rounded ${l.window_total >= 0 ? 'left-1/2 bg-emerald-500/60' : 'right-1/2 bg-red-500/60'}`} style={{ width: `${(Math.abs(l.window_total) / maxLead) * 50}%` }} />
                  <div className="absolute left-1/2 top-0 h-3 w-px bg-slate-600" />
                </div>
                <span className={`w-16 text-right font-mono ${netColor(l.window_total)}`}>{fMln(l.window_total)}</span>
              </div>
            ))}
          </div>
          <p className="mt-4 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.05] p-3 text-[11px] text-emerald-200/80">
            Real US spot Bitcoin ETF daily net flows (USD millions) via {d.source}. Farside is the canonical source; we read a live mirror because Farside blocks automated access. Latest data: {d.latest_date}.
          </p>
        </>
      )}
    </Card>
  );
}

function WhaleImpactCard() {
  const [d, setD] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/v1/whales/impact`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => { if (alive) { setD(j); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  const fBtc = (v) => (v == null ? '—' : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }) + ' BTC');
  const fChg = (v) => (v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }));
  const trendColor = (t) => t === 'Accumulation' ? 'text-emerald-400' : t === 'Distribution' ? 'text-red-400' : 'text-slate-300';
  const contribs = (d && d.contributors) || [];
  return (
    <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Waves className="h-5 w-5 text-sky-400" />
        <h3 className="flex items-center gap-1 font-semibold text-white">Whale Impact (30-day)<InfoTip below text="Aggregate accumulation vs distribution across the tracked whales over ~30 days, reconstructed from real on-chain transactions. Exchange OUTFLOWS count as bullish (supply leaving exchanges); holder accumulation counts as bullish." /></h3>
        <span className="rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300">Live</span>
      </div>
      {loading ? (
        <p className="text-sm text-slate-500">Reconstructing whale balance history (this can take a moment on first load)…</p>
      ) : !d || d.status !== 'ready' ? (
        <p className="text-sm text-slate-500">Impact data is computing — check back shortly.</p>
      ) : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><div className="text-[11px] text-slate-500">30d net flow</div><div className={`text-lg font-semibold ${trendColor(d.trend)}`}>{fChg(d.net_flow_30d)} BTC</div></div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><div className="text-[11px] text-slate-500">Trend</div><div className={`text-lg font-semibold ${trendColor(d.trend)}`}>{d.trend}</div></div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><div className="text-[11px] text-slate-500">Held by holders</div><div className="text-lg font-semibold text-white">{fBtc(d.holder_balance)}</div></div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><div className="text-[11px] text-slate-500">On exchanges</div><div className="text-lg font-semibold text-white">{fBtc(d.exchange_balance)}</div></div>
          </div>
          {contribs.length > 0 && (
            <>
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Biggest movers (30d)</div>
              <div className="space-y-1.5">
                {contribs.map((c, i) => (
                  <div key={i} className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-2.5 text-sm">
                    <span className="flex-1 truncate text-slate-200">{c.name} <span className="text-[10px] text-slate-500">· {c.category}</span></span>
                    <span className={`font-mono ${c.delta_30d >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{fChg(c.delta_30d)} BTC</span>
                    <span className={`w-16 text-right text-xs font-semibold ${sigColor(c.signal)}`}>{c.signal}</span>
                  </div>
                ))}
              </div>
            </>
          )}
          <p className="mt-4 text-[11px] text-slate-500">{d.note}</p>
        </>
      )}
    </Card>
  );
}

function WhaleTxFeed() {
  const [d, setD] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [minBtc, setMinBtc] = React.useState(50);
  React.useEffect(() => {
    let alive = true; setLoading(true);
    fetch(`${API_BASE}/v1/whales/transactions?min_btc=${minBtc}&limit=40`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => { if (alive) { setD(j); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [minBtc]);
  const feed = (d && d.feed) || [];
  const fUsd = (v) => (v == null ? '' : '$' + (v >= 1e9 ? (v / 1e9).toFixed(2) + 'B' : (v / 1e6).toFixed(1) + 'M'));
  const dt = (iso) => { try { return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); } catch { return iso; } };
  return (
    <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Activity className="h-5 w-5 text-sky-400" />
        <h3 className="flex items-center gap-1 font-semibold text-white">Large Transactions<InfoTip below text="A live, time-sorted feed of notable on-chain moves across the tracked whales, each labelled with the known entity. Exchange inflows hint at potential selling; outflows and holder accumulation read bullish." /></h3>
        <span className="rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300">Live</span>
        <div className="ml-auto flex items-center gap-1 text-[11px] text-slate-400">
          <span>min</span>
          {[50, 100, 500, 1000].map((v) => (
            <button key={v} onClick={() => setMinBtc(v)} className={`rounded px-1.5 py-0.5 font-semibold ${minBtc === v ? 'bg-sky-500/20 text-sky-300 ring-1 ring-sky-500/40' : 'text-slate-500 hover:text-slate-300'}`}>{v}</button>
          ))}
          <span>BTC</span>
        </div>
      </div>
      {loading ? (
        <p className="text-sm text-slate-500">Scanning recent large transfers…</p>
      ) : !feed.length ? (
        <p className="text-sm text-slate-500">No transfers ≥ {minBtc} BTC found in the recent window for the tracked whales.</p>
      ) : (
        <div className="space-y-1.5">
          {feed.map((e, i) => (
            <a key={i} href={`https://mempool.space/tx/${e.txid}`} target="_blank" rel="noreferrer" className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-xs hover:border-slate-700">
              {e.direction === 'in' ? <ArrowDownRight className="h-4 w-4 text-emerald-400" /> : <ArrowUpRight className="h-4 w-4 text-red-400" />}
              <span className="min-w-[120px] flex-1 font-semibold text-slate-100">{e.entity} <span className="text-[10px] font-normal text-slate-500">· {e.category}</span></span>
              <span className="font-mono text-slate-200">{Number(e.amount).toLocaleString(undefined, { maximumFractionDigits: 1 })} BTC</span>
              <span className="w-20 text-right text-slate-500">{fUsd(e.amount_usd)}</span>
              <span className={`w-40 text-right text-[11px] font-semibold ${sigColor(e.signal)}`}>{e.impact}</span>
              <span className="w-28 text-right text-slate-500">{dt(e.date)}</span>
            </a>
          ))}
        </div>
      )}
      <p className="mt-4 text-[11px] text-slate-500">{d && d.source} · Tap any row to open the transaction in a block explorer. Only wallets with public labels are named — deep clustering of unknown wallets needs a paid provider.</p>
    </Card>
  );
}

function WhaleHistoryChart({ address }) {
  const [d, setD] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    let alive = true; setLoading(true);
    fetch(`${API_BASE}/v1/whales/history?address=${address}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => { if (alive) { setD(j); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [address]);
  if (loading) return <p className="text-xs text-slate-500">Reconstructing balance history from on-chain transactions…</p>;
  const pts = (d && d.points) || [];
  if (!pts.length) return <p className="text-xs text-slate-500">Not enough on-chain history to chart this wallet.</p>;
  const chart = pts.map((p) => ({ date: p.date, bal: p.bal }));
  const fChg = (v) => (v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }) + ' BTC');
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3 text-[11px]">
        <span className="font-semibold uppercase tracking-wide text-slate-500">Balance history</span>
        <span className="text-slate-400">30d <span className={d.change_30d >= 0 ? 'text-emerald-400' : 'text-red-400'}>{fChg(d.change_30d)}</span></span>
        <span className="text-slate-400">90d <span className={d.change_90d >= 0 ? 'text-emerald-400' : 'text-red-400'}>{fChg(d.change_90d)}</span></span>
        <span className="ml-auto text-slate-600">{d.span_from} → {d.span_to}</span>
      </div>
      <div className="h-32 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chart} margin={{ top: 4, right: 6, left: -14, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#64748b' }} tickLine={false} axisLine={{ stroke: '#1e293b' }} minTickGap={30} tickFormatter={shortDate} />
            <YAxis tick={{ fontSize: 9, fill: '#64748b' }} tickLine={false} axisLine={false} width={48} domain={['auto', 'auto']} tickFormatter={(v) => (v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v)} />
            <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} formatter={(v) => [Number(v).toLocaleString() + ' BTC', 'Balance']} />
            <Line type="stepAfter" dataKey="bal" stroke="#38bdf8" strokeWidth={1.6} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-[10px] text-slate-600">Reconstructed from this address's real on-chain transactions (mempool.space). Depth depends on how active the wallet is.</p>
    </div>
  );
}


function WhaleWatch() {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [openAddr, setOpenAddr] = React.useState(null);
  const [acts, setActs] = React.useState({});
  const [actLoading, setActLoading] = React.useState(false);
  React.useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/v1/whales`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => { if (alive) { setData(j); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  const toggle = (addr) => {
    if (openAddr === addr) { setOpenAddr(null); return; }
    setOpenAddr(addr);
    if (!acts[addr]) {
      setActLoading(true);
      fetch(`${API_BASE}/v1/whale-activity?address=${addr}&limit=10`, { cache: 'no-store' })
        .then((r) => r.json())
        .then((j) => { setActs((p) => ({ ...p, [addr]: j })); setActLoading(false); })
        .catch(() => setActLoading(false));
    }
  };
  const actTime = (t) => t ? new Date(t * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Pending';
  const whales = (data && data.whales) || [];
  const catStyle = (c) => ({
    Exchange: 'text-sky-300 bg-sky-500/10 border-sky-500/25',
    Government: 'text-amber-300 bg-amber-500/10 border-amber-500/25',
    Whale: 'text-violet-300 bg-violet-500/10 border-violet-500/25',
    Treasury: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/25',
  }[c] || 'text-slate-300 bg-slate-800/40 border-slate-700');
  const fBtc = (v) => v == null ? '—' : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }) + ' BTC';
  const fUsd = (v) => v == null ? '' : '$' + (v >= 1e9 ? (v / 1e9).toFixed(2) + 'B' : (v / 1e6).toFixed(1) + 'M');
  const fChg = (v) => v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }) + ' BTC';
  const total = whales.reduce((s, w) => s + (w.balance || 0), 0);
  return (
    <div className="space-y-5">
      <SectionHead icon={Fish} title="Whale Watch" blurb={sec('whales').blurb} coin="BTC" />
      <AiReview section="whales" text="Albert is reviewing whale flows and ETF demand…" voice />
      <WhaleImpactCard />
      <ExchangeNetFlowCard />
      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Fish className="h-5 w-5 text-sky-400" />
          <h3 className="font-semibold text-white">Largest labeled Bitcoin wallets</h3>
          <span className="rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300">Live</span>
          <span className="ml-auto text-[11px] text-slate-500">{data && data.source}</span>
        </div>
        {loading ? (
          <p className="text-sm text-slate-500">Loading live on-chain balances…</p>
        ) : whales.length === 0 ? (
          <p className="text-sm text-slate-500">No whale data yet — balances are fetched live and cached; check back in a moment.</p>
        ) : (
          <>
            <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><div className="text-[11px] text-slate-500">Wallets tracked</div><div className="text-lg font-semibold text-white">{whales.length}</div></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><div className="text-[11px] text-slate-500">Combined balance</div><div className="text-lg font-semibold text-white">{fBtc(total)}</div></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><div className="text-[11px] text-slate-500">BTC price</div><div className="text-lg font-semibold text-white">{data.price ? '$' + Number(data.price).toLocaleString() : '—'}</div></div>
            </div>
            <div className="space-y-2">
              {whales.map((w, i) => {
                const isOpen = openAddr === w.address;
                const act = acts[w.address];
                return (
                <div key={i} className={`rounded-lg border ${isOpen ? 'border-sky-500/40 bg-slate-950/60' : 'border-slate-800 bg-slate-950/40'}`}>
                  <button onClick={() => toggle(w.address)} className="flex w-full flex-wrap items-center gap-3 p-3 text-left transition hover:bg-slate-900/60">
                    <CoinIcon symbol="BTC" size={20} />
                    <div className="min-w-[150px] flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-100">{w.name}</span>
                        <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${catStyle(w.category)}`}>{w.category}</span>
                      </div>
                      <a href={`https://mempool.space/address/${w.address}`} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="font-mono text-[11px] text-slate-500 hover:text-sky-400">{w.address.slice(0, 10)}…{w.address.slice(-6)}</a>
                    </div>
                    {w.spark && <Spark data={w.spark} color={sigHex(w.signal)} />}
                    <div className="text-right">
                      <div className="font-mono text-sm text-slate-100">{fBtc(w.balance)}</div>
                      <div className="text-[11px] text-slate-500">{fUsd(w.balance_usd)}</div>
                    </div>
                    <div className="w-24 text-right">
                      <div className="text-[10px] uppercase tracking-wide text-slate-600">7d change</div>
                      <div className={`text-xs font-semibold ${w.change_7d == null ? 'text-slate-500' : w.change_7d >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{fChg(w.change_7d)}</div>
                    </div>
                    <span className={`w-16 text-right text-xs font-semibold ${sigColor(w.signal)}`}>{w.signal}</span>
                    <ChevronDown className={`h-4 w-4 text-slate-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {isOpen && (
                    <div className="border-t border-slate-800 p-3">
                      <div className="mb-3 rounded-lg border border-slate-800/70 bg-slate-900/40 p-3">
                        <WhaleHistoryChart address={w.address} />
                      </div>
                      <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                        <Activity className="h-3.5 w-3.5" /> Recent activity {act && act.notable_only && <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[9px] normal-case text-slate-400">notable moves ≥ 0.1 BTC</span>}
                      </div>
                      {actLoading && !act ? (
                        <p className="text-xs text-slate-500">Loading on-chain activity…</p>
                      ) : (act && act.activity && act.activity.length) ? (
                        <div className="space-y-1">
                          {act.activity.map((x, k) => (
                            <a key={k} href={`https://mempool.space/tx/${x.txid}`} target="_blank" rel="noreferrer" className="flex items-center gap-2 rounded border border-slate-800/70 bg-slate-900/40 px-2.5 py-1.5 text-xs hover:border-slate-700">
                              {x.direction === 'in'
                                ? <ArrowDownRight className="h-3.5 w-3.5 text-emerald-400" />
                                : <ArrowUpRight className="h-3.5 w-3.5 text-red-400" />}
                              <span className={`font-semibold ${x.direction === 'in' ? 'text-emerald-400' : 'text-red-400'}`}>{x.direction === 'in' ? 'Received' : 'Sent'}</span>
                              <span className="font-mono text-slate-200">{Number(x.amount).toLocaleString(undefined, { maximumFractionDigits: 4 })} BTC</span>
                              <span className="ml-auto text-slate-500">{actTime(x.time)}</span>
                              {!x.confirmed && <span className="rounded bg-amber-500/15 px-1 text-[9px] text-amber-300">pending</span>}
                            </a>
                          ))}
                          <p className="pt-1 text-[10px] text-slate-600">Net effect on this wallet per transaction. Tap a row to open it in a block explorer.</p>
                        </div>
                      ) : (
                        <p className="text-xs text-slate-500">No recent activity found for this wallet.</p>
                      )}
                    </div>
                  )}
                </div>
                );
              })}
            </div>
            <p className="mt-4 rounded-lg border border-slate-500/20 bg-slate-500/[0.05] p-3 text-[11px] text-slate-400">
              Balances are fetched live from the Bitcoin blockchain (mempool.space / blockchain.com). Entity names are curated from public labels and may not cover every wallet an entity controls. Accumulation / distribution signals activate once a few days of history accrue. Exchange <span className="text-emerald-400">outflows</span> read bullish (coins leaving to storage); <span className="text-red-400">inflows</span> read bearish.
            </p>
          </>
        )}
      </Card>
      <WhaleTxFeed />
    </div>
  );
}


export { EtfFlowsCard };
export default WhaleWatch;
