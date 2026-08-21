'use client';

import React from 'react';
import { Brain, Gauge, History, Lock, Activity, Zap } from 'lucide-react';
import { ResponsiveContainer, ComposedChart, Line, Area, Bar, BarChart, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, Cell } from 'recharts';
import { Card } from '@/components/ui/card';
import { API_BASE } from '../lib/api';
import { riskColor, TF_TOUCH } from '../lib/format';
import { sec } from '../lib/sections';
import { SectionHead, AiReview, InfoTip, DemoBadge, LevGauge } from './shared';

function LiveOrderFlow() {
  const [o, setO] = React.useState(null);
  React.useEffect(() => {
    let alive = true;
    const tick = () => fetch(`${API_BASE}/v1/orderflow`, { cache: 'no-store' })
      .then((r) => r.json()).then((j) => { if (alive) setO(j); }).catch(() => {});
    tick();
    const id = setInterval(tick, 2500);
    return () => { alive = false; clearInterval(id); };
  }, []);
  if (!o) return null;
  const live = o.status === 'live';
  const liq = o.liquidations || {};
  const cvdUp = (o.cvd_window_btc ?? 0) >= 0;
  const fUsd = (v) => (v == null ? '—' : '$' + (Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(2) + 'M' : Math.abs(v) >= 1e3 ? (v / 1e3).toFixed(0) + 'k' : Math.round(v)));
  const flowColor = o.flow_state === 'Aggressive buying' ? '#34d399' : o.flow_state === 'Aggressive selling' ? '#f87171' : '#94a3b8';
  return (
    <Card className="border-0 bg-slate-900 p-4 ring-1 ring-slate-800">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-white"><Activity className="h-4 w-4 text-sky-400" />Live Order Flow</h3>
        <InfoTip below text="Real-time trade flow from Coinbase + Bybit WebSocket streams, aggregated every second. CVD = cumulative volume delta (buy − sell BTC). OFI = order-flow imbalance per second. VPIN ≈ order-flow toxicity (0–1, higher = more one-sided). Liquidation cascade watch flags >$1M force-liquidated in 10s." />
        <span className={`ml-auto flex items-center gap-1 text-[10px] font-bold ${live ? 'text-emerald-400' : 'text-amber-400'}`}>
          <span className={`h-2 w-2 rounded-full ${live ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />{live ? 'LIVE' : (o.status || 'connecting').toUpperCase()}
        </span>
      </div>
      {o.status === 'connecting' ? (
        <p className="text-sm text-slate-500">{o.message || 'Order-flow pipeline warming up…'}</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase text-slate-500">Flow (1m)</p><p className="mt-1 text-sm font-black" style={{ color: flowColor }}>{o.flow_state}</p><p className="text-[10px] text-slate-600">{o.buy_ratio_pct}% buys</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase text-slate-500">CVD (1m)</p><p className="mt-1 text-sm font-black" style={{ color: cvdUp ? '#34d399' : '#f87171' }}>{cvdUp ? '+' : ''}{o.cvd_window_btc} BTC</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase text-slate-500">OFI /s</p><p className="mt-1 text-sm font-black text-slate-100">{o.ofi_btc_per_s}</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase text-slate-500">VPIN</p><p className="mt-1 text-sm font-black" style={{ color: (o.vpin ?? 0) > 0.6 ? '#fbbf24' : '#34d399' }}>{o.vpin}</p></div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase text-slate-500">Trades/s</p><p className="mt-1 text-sm font-black text-slate-100">{o.trades_per_sec}</p></div>
            <div className={`rounded-xl border p-3 ${liq.cascade_risk ? 'border-red-500/40 bg-red-500/10' : 'border-slate-800 bg-slate-950/50'}`}><p className="text-[10px] uppercase text-slate-500 flex items-center gap-1"><Zap className="h-3 w-3" />Liq (1m)</p><p className="mt-1 text-sm font-black" style={{ color: liq.cascade_risk ? '#f87171' : '#e2e8f0' }}>{fUsd((liq.long_usd_1m || 0) + (liq.short_usd_1m || 0))}</p><p className="text-[10px] text-slate-600">{liq.cascade_risk ? 'cascade risk' : `L ${fUsd(liq.long_usd_1m)} / S ${fUsd(liq.short_usd_1m)}`}</p></div>
          </div>
          {(o.history || []).length > 3 && (
            <div className="mt-3">
              <p className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-500"><span>Session CVD trend (~90s)</span><span className="normal-case text-slate-600">net liq/1m: {fUsd(liq.net_usd_1m)}</span></p>
              <div className="h-16 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={o.history} margin={{ top: 2, right: 2, left: 2, bottom: 0 }}>
                    <YAxis hide domain={['dataMin', 'dataMax']} />
                    <XAxis dataKey="t" hide />
                    <ReferenceLine y={0} stroke="#334155" strokeDasharray="2 2" />
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 11 }}
                      labelFormatter={() => ''} formatter={(v) => [`${v} BTC`, 'Session CVD']} />
                    <Line dataKey="cvd" stroke={cvdUp ? '#34d399' : '#f87171'} strokeWidth={1.5} dot={false} isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
          {o.orderbook && o.orderbook.bins && o.orderbook.bins.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-500">
                <span>Resting liquidity (±{o.orderbook.band_pct}%)</span>
                <span className="normal-case text-slate-600">walls: <span className="text-emerald-400">bid {fUsd(o.orderbook.max_bid_wall?.usd)}</span> · <span className="text-red-400">ask {fUsd(o.orderbook.max_ask_wall?.usd)}</span></span>
              </p>
              <div className="flex h-10 w-full overflow-hidden rounded-md ring-1 ring-slate-800">
                {(() => {
                  const bins = o.orderbook.bins;
                  const mx = Math.max(1, ...bins.map((b) => Math.max(b.bid_usd || 0, b.ask_usd || 0)));
                  return bins.map((b, i) => {
                    const isBid = (b.bid_usd || 0) >= (b.ask_usd || 0);
                    const usd = isBid ? (b.bid_usd || 0) : (b.ask_usd || 0);
                    const a = Math.min(1, usd / mx);
                    const bg = usd <= 0 ? 'transparent' : isBid ? `rgba(52,211,153,${0.12 + a * 0.78})` : `rgba(248,113,113,${0.12 + a * 0.78})`;
                    return <div key={i} title={`$${Math.round(b.price).toLocaleString()} · ${isBid ? 'bids' : 'asks'} ${fUsd(usd)}`} className="flex-1 border-r border-slate-950/40" style={{ background: bg }} />;
                  });
                })()}
              </div>
              <div className="mt-0.5 flex justify-between text-[9px] text-slate-600"><span>−{o.orderbook.band_pct}% (bids)</span><span>mid ${Math.round(o.orderbook.mid).toLocaleString()}</span><span>+{o.orderbook.band_pct}% (asks)</span></div>
            </div>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-600">
            {Object.entries(o.venues || {}).map(([v, st]) => (
              <span key={v} className="flex items-center gap-1"><span className={`h-1.5 w-1.5 rounded-full ${st === 'live' ? 'bg-emerald-400' : 'bg-amber-400'}`} />{v}</span>
            ))}
            <span className="ml-auto italic">WebSocket → Redis Streams → 1s aggregator{o.redis ? '' : ' (in-memory)'}</span>
          </div>
        </>
      )}
    </Card>
  );
}


function LeverageSection() {
  const [tf, setTf] = React.useState('4H');
  const [emphasis, setEmphasis] = React.useState('LONG');
  const [heatSide, setHeatSide] = React.useState('combined');
  const [d, setD] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    let alive = true; setLoading(true);
    fetch(`${API_BASE}/v1/leverage?timeframe=${tf}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => { if (alive) { setD(j); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [tf]);

  const fUsd = (v) => v == null ? '—' : '$' + (Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(2) + 'B' : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : Number(v).toLocaleString());
  const pressColor = (p) => ({ LOW: 'text-emerald-400', MODERATE: 'text-lime-400', ELEVATED: 'text-amber-400', HIGH: 'text-orange-400', EXTREME: 'text-red-400' }[p] || 'text-slate-300');
  const biasColor = (b) => b === 'Long Dominant' ? 'text-emerald-400' : b === 'Short Dominant' ? 'text-red-400' : 'text-slate-300';
  const sqColor = (x) => x === 'Long Squeeze Risk' ? 'text-red-400' : x === 'Short Squeeze Risk' ? 'text-emerald-400' : 'text-slate-300';
  const riskColor = (l) => ({ Low: 'text-emerald-400', Normal: 'text-lime-400', Moderate: 'text-amber-400', Elevated: 'text-orange-400', High: 'text-red-400', Extreme: 'text-red-400' }[l] || 'text-slate-300');
  const ttime = (t) => { try { return new Date(t).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }); } catch { return ''; } };

  if (loading && !d) return (<div className="space-y-5"><SectionHead icon={Gauge} title="Leverage" blurb={sec('leverage').blurb} coin="BTC" /><Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800"><p className="text-sm text-slate-500">Loading live leverage data (OKX)…</p></Card></div>);
  if (!d || d.status !== 'ready') return (<div className="space-y-5"><SectionHead icon={Gauge} title="Leverage" blurb={sec('leverage').blurb} coin="BTC" /><Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800"><p className="text-sm text-slate-500">Leverage data is computing — check back in a moment.</p></Card></div>);

  const s = d.summary || {}, p = d.positioning || {}, oi = d.open_interest || {}, f = d.funding || {}, el = d.estimated_leverage || {}, lq = d.liquidations || {}, sq = d.squeeze || {}, bm = d.bitmark || {}, ac = d.albert_call || {};
  const oiChart = (oi.series || []).map((x) => ({ t: x.t, oi: x.oi, price: x.price })).filter((x) => x.oi);
  const fChart = (f.series || []).map((x) => ({ t: x.t, rate: x.rate }));
  const liqBars = [['1h', lq.long_1h, lq.short_1h], ['4h', lq.long_4h, lq.short_4h], ['24h', lq.long_24h, lq.short_24h]].map(([w, l, sh]) => ({ w, long: l, short: sh }));
  const heat = ((d.heatmap && d.heatmap.zones) || []).filter((z) => heatSide === 'combined' ? true : z.side === heatSide);
  const maxInt = Math.max(0.01, ...heat.map((z) => z.intensity || 0));

  return (
    <div className="space-y-5">
      <SectionHead icon={Gauge} title="Leverage" blurb="Long & short positioning, market leverage and liquidation pressure" coin="BTC" />

      <LiveOrderFlow />

      <Card className="border-0 bg-slate-900 p-4 ring-1 ring-slate-800">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div><div className="text-[11px] text-slate-500">BTC price</div><div className="text-lg font-bold text-white">{d.price ? '$' + Number(d.price).toLocaleString() : '—'} <span className={`text-xs font-semibold ${(d.price_change_24h || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{(d.price_change_24h >= 0 ? '+' : '')}{d.price_change_24h}%</span></div></div>
          <div><div className="text-[11px] text-slate-500">Updated</div><div className="text-sm text-slate-300">{ttime(d.as_of)}</div></div>
          <div className="ml-auto flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-950/40 p-1">
            {['1H', '4H', '1D', '7D'].map((x) => (<button key={x} onClick={() => setTf(x)} className={`${TF_TOUCH} rounded px-2.5 py-1 text-xs font-semibold ${tf === x ? 'bg-sky-500/20 text-sky-300 ring-1 ring-sky-500/40' : 'text-slate-500 hover:text-slate-300'}`}>{x}</button>))}
          </div>
          <div className="flex overflow-hidden rounded-lg border border-slate-800">
            {['LONG', 'SHORT'].map((x) => (<button key={x} onClick={() => setEmphasis(x)} className={`px-4 py-1.5 text-xs font-bold ${emphasis === x ? (x === 'LONG' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300') : 'bg-slate-950/40 text-slate-500 hover:text-slate-300'}`}>{x}</button>))}
          </div>
        </div>
      </Card>

      <AiReview section="institutional" text="Albert is reviewing leverage & positioning…" voice />

      <Card className="border-0 bg-gradient-to-br from-slate-900 to-slate-900/60 p-6 ring-1 ring-slate-800">
        <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4"><div className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-slate-500">Leverage Pressure<InfoTip below text="How aggressive leveraged positioning is overall, combining open interest, funding, positioning skew and estimated leverage. Higher = more fragile to fast moves." /></div><div className={`text-3xl font-black ${pressColor(s.pressure)}`}>{s.pressure}</div><div className="text-[11px] text-slate-600">score {s.pressure_score}/100</div></div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4"><div className="text-[11px] uppercase tracking-wider text-slate-500">Market Bias</div><div className={`text-2xl font-black ${biasColor(s.bias)}`}>{s.bias}</div></div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4"><div className="text-[11px] uppercase tracking-wider text-slate-500">Squeeze Risk</div><div className={`text-2xl font-black ${sqColor(s.squeeze)}`}>{s.squeeze}</div></div>
        </div>
        <p className="rounded-lg border border-sky-500/20 bg-sky-500/[0.05] p-3 text-sm text-slate-300">{s.interpretation}</p>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <h3 className="mb-4 flex items-center gap-1 font-semibold text-white">Long vs Short Positioning<InfoTip below text="Share of leveraged accounts positioned long vs short (OKX). A ratio above 1 means more accounts are long than short." /></h3>
          <div className="mb-1 flex justify-between text-sm font-semibold"><span className="text-emerald-400">Long {p.long_pct}%</span><span className="text-red-400">{p.short_pct}% Short</span></div>
          <div className="flex h-6 overflow-hidden rounded-lg"><div className="bg-emerald-500/70" style={{ width: `${p.long_pct}%` }} /><div className="bg-red-500/70" style={{ width: `${p.short_pct}%` }} /></div>
          <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
            <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[11px] text-slate-500">L/S Account Ratio</div><div className="font-mono text-slate-100">{p.account_ratio} <span className="text-[11px] text-slate-500">(prev {p.account_ratio_prev})</span></div></div>
            <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="flex items-center gap-1 text-[11px] text-slate-500">L/S Position Ratio<DemoBadge label="No data" /></div><div className="font-mono text-slate-500">No data available</div></div>
          </div>
          <p className="mt-3 text-xs text-slate-400">Change over {d.timeframe}: <span className={`font-semibold ${(p.ratio_change_tf || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{(p.ratio_change_tf >= 0 ? '+' : '')}{p.ratio_change_tf}</span> · {p.trend}</p>
        </Card>

        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <h3 className="mb-3 flex items-center gap-1 font-semibold text-white">Open Interest<InfoTip below text="Total value of leveraged futures positions currently open. Rising OI means new leveraged money entering; falling OI means positions closing." /></h3>
          <div className="mb-3 flex flex-wrap items-end gap-4"><div><div className="text-2xl font-bold text-white">{fUsd(oi.value_usd)}</div><div className="text-[11px] text-slate-500">aggregate OI</div></div><div className={`text-sm font-semibold ${(oi.change_tf_pct || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{(oi.change_tf_pct >= 0 ? '+' : '')}{oi.change_tf_pct}% <span className="text-[11px] text-slate-500">/ {d.timeframe}</span></div><span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${oi.state === 'Rising' ? 'border-emerald-500/40 text-emerald-300' : oi.state === 'Falling' ? 'border-red-500/40 text-red-300' : 'border-slate-600 text-slate-400'}`}>{oi.state}</span></div>
          <div className="h-32 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={oiChart} margin={{ top: 4, right: 4, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="t" hide />
                <YAxis yAxisId="p" hide domain={['auto', 'auto']} />
                <YAxis yAxisId="oi" hide domain={['auto', 'auto']} />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }} labelFormatter={() => ''} formatter={(v, n) => [n === 'price' ? '$' + Number(v).toLocaleString() : fUsd(v), n === 'price' ? 'Price' : 'OI']} />
                <Area yAxisId="oi" type="monotone" dataKey="oi" stroke="#a78bfa" fill="#a78bfa22" strokeWidth={1.4} dot={false} />
                <Line yAxisId="p" type="monotone" dataKey="price" stroke="#38bdf8" strokeWidth={1.6} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-[11px] text-slate-400">{oi.interpretation}</p>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <h3 className="mb-3 flex items-center gap-1 font-semibold text-white">Funding Rates<InfoTip below text="Periodic payment between longs and shorts on perpetual futures. Positive = longs pay shorts (long demand); negative = shorts pay longs." /></h3>
          <div className="mb-3 flex flex-wrap items-center gap-3"><div className={`text-2xl font-bold ${f.rate >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{(f.rate >= 0 ? '+' : '')}{f.rate}%</div><span className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400">{f.direction} · {f.trend}</span><span className={`ml-auto rounded border px-2 py-0.5 text-xs font-semibold ${f.bias === 'Long Bias' ? 'border-emerald-500/40 text-emerald-300' : f.bias === 'Short Bias' ? 'border-red-500/40 text-red-300' : 'border-slate-600 text-slate-400'}`}>{f.bias}</span></div>
          <div className="h-20 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={fChart} margin={{ top: 2, right: 2, left: -20, bottom: 0 }}>
                <ReferenceLine y={0} stroke="#475569" />
                <YAxis hide /><XAxis dataKey="t" hide />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }} labelFormatter={() => ''} formatter={(v) => [v + '%', 'Funding']} />
                <Bar dataKey="rate">{fChart.map((x, i) => <Cell key={i} fill={x.rate >= 0 ? '#34d399' : '#f87171'} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">{(f.exchanges || []).map((e, i) => (<span key={i} className="rounded border border-slate-800 bg-slate-950/40 px-2 py-0.5 text-[11px] text-slate-300">{e.name}: <span className={e.rate >= 0 ? 'text-emerald-400' : 'text-red-400'}>{(e.rate >= 0 ? '+' : '')}{e.rate}%</span></span>))}</div>
          <p className="mt-2 text-[11px] text-slate-400">{f.interpretation}</p>
        </Card>

        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <h3 className="mb-3 flex items-center gap-1 font-semibold text-white">Estimated Leverage<DemoBadge label="No data" /><InfoTip below text="An estimate of how much leverage is in the system relative to recent conditions. Higher leverage tends to amplify volatility. Requires a live leverage/exchange-reserve feed." /></h3>
          <div className="flex h-28 flex-col items-center justify-center rounded-lg border border-dashed border-slate-700 bg-slate-950/30 p-4 text-center">
            <Lock className="mb-2 h-5 w-5 text-slate-600" />
            <div className="text-sm font-semibold text-slate-400">No data available</div>
            <p className="mt-1 text-[11px] text-slate-500">{el.reason || 'Requires a paid derivatives-data feed to activate.'}</p>
          </div>
        </Card>
      </div>

      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <h3 className="mb-3 flex items-center gap-1 font-semibold text-white">Liquidations<DemoBadge label="No data" /><InfoTip below text="Dollar value of leveraged positions force-closed as price moved against them. Long liquidations spike when price drops; short liquidations spike when price rises. Requires a live liquidations feed." /></h3>
        <div className="flex h-28 flex-col items-center justify-center rounded-lg border border-dashed border-slate-700 bg-slate-950/30 p-4 text-center">
          <Lock className="mb-2 h-5 w-5 text-slate-600" />
          <div className="text-sm font-semibold text-slate-400">No data available</div>
          <p className="mt-1 text-[11px] text-slate-500">{lq.reason || 'Real-time long/short liquidation totals require a paid feed (e.g. CoinGlass).'}</p>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <div className="mb-3 flex flex-wrap items-center gap-2"><h3 className="flex items-center gap-1 font-semibold text-white">Liquidation Heatmap<DemoBadge label="No data" /><InfoTip below text="Estimated price zones where clusters of leveraged positions could be liquidated. Requires a live liquidation-level feed (e.g. CoinGlass)." /></h3></div>
          <div className="flex h-40 flex-col items-center justify-center rounded-lg border border-dashed border-slate-700 bg-slate-950/30 p-4 text-center">
            <Lock className="mb-2 h-6 w-6 text-slate-600" />
            <div className="text-sm font-semibold text-slate-400">No data available</div>
            <p className="mt-1 max-w-xs text-[11px] text-slate-500">{(d.heatmap && d.heatmap.reason) || 'Liquidation-level heatmap data requires a paid feed. Current BTC price:'} {d.price ? <span className="font-mono text-sky-300">${Number(d.price).toLocaleString()}</span> : null}</p>
          </div>
        </Card>

        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <h3 className="mb-4 flex items-center gap-1 font-semibold text-white">Squeeze Risk<InfoTip below text="A long squeeze is when falling price forces leveraged longs to sell; a short squeeze is when rising price forces leveraged shorts to buy back. Higher score = more vulnerable." /></h3>
          <div className="flex justify-around">
            <div className="text-center"><LevGauge value={sq.long_risk} label={`Long ${sq.long_label}`} color="#f87171" /></div>
            <div className="text-center"><LevGauge value={sq.short_risk} label={`Short ${sq.short_label}`} color="#34d399" /></div>
          </div>
          <p className="mt-3 text-[11px] text-slate-400">{emphasis === 'LONG' ? sq.long_explain : sq.short_explain}</p>
        </Card>
      </div>

      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <h3 className="mb-3 flex items-center gap-2 font-semibold text-white"><Brain className="h-5 w-5 text-sky-400" />BitMarkAI Leverage Intelligence</h3>
        <ul className="space-y-1.5">{(bm.observations || []).map((o, i) => (<li key={i} className="flex gap-2 text-sm text-slate-300"><span className="text-sky-500">•</span>{o}</li>))}</ul>
        <div className="mt-4 rounded-lg border border-sky-500/20 bg-sky-500/[0.05] p-3"><div className="text-[11px] uppercase tracking-wider text-slate-500">Overall Leverage Assessment</div><div className="text-lg font-bold text-white">{bm.assessment_title}</div><p className="mt-1 text-sm text-slate-300">{bm.assessment_text}</p></div>
      </Card>

      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <h3 className="mb-2 flex items-center gap-2 font-semibold text-white"><img src="/albert.png" alt="Albert" className="h-6 w-6 rounded-full" onError={(e) => { e.currentTarget.style.display = 'none'; }} />Impact on Albert's Call</h3>
        <div className="flex items-center gap-3"><span className="text-[11px] text-slate-500">Currently:</span><span className={`text-lg font-bold ${ac.impact_points < 0 ? 'text-red-400' : ac.impact_points > 0 ? 'text-emerald-400' : 'text-slate-300'}`}>{ac.impact_label} {ac.impact_points >= 0 ? '+' : ''}{ac.impact_points}</span></div>
        <p className="mt-2 text-sm text-slate-300">{ac.explanation}</p>
      </Card>

      <Card className="border-0 bg-slate-900/60 p-4 ring-1 ring-slate-800">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Data sources</div>
        <ul className="space-y-1 text-[11px] text-slate-400">{(d.sources || []).map((x, i) => (<li key={i}>• {x}</li>))}</ul>
        <p className="mt-3 border-t border-slate-800 pt-3 text-[11px] italic text-slate-500">{d.disclaimer}</p>
      </Card>
    </div>
  );
}

/* ---------------- Whale Intelligence: ETF Flows / Impact / Tx feed / History ---------------- */

export default LeverageSection;
