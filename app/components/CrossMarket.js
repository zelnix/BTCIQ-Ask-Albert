'use client';

import React from 'react';
import { Globe } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine } from 'recharts';
import { Card } from '@/components/ui/card';
import { API_BASE } from '../lib/api';
import { SymbolContext } from '../lib/context';
import { sec } from '../lib/sections';
import { TF_TOUCH } from '../lib/format';
import { SectionHead, AiReview, TapInfo } from './shared';

const COMPARE_NAMES = { BTC: 'Bitcoin', ETH: 'Ethereum', SOL: 'Solana' };


const MK_COLORS = ['#f7931a', '#38bdf8', '#a78bfa', '#34d399', '#f472b6', '#facc15', '#fb923c', '#22d3ee', '#e879f9', '#94a3b8'];
const MK_WINDOWS = [['1m', '1M'], ['3m', '3M'], ['6m', '6M'], ['ytd', 'YTD'], ['1y', '1Y']];
const mkPct = (v) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v}%`);
const mkPctColor = (v) => (v == null ? 'text-slate-500' : v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300');

function reviewCrossMarket(d) {
  if (!d) return 'Loading the cross-market comparison…';
  const coin = d.coin_name;
  const cr = (d.table || []).find((t) => t.is_coin);
  const wlabel = (MK_WINDOWS.find((w) => w[0] === d.window) || [])[1] || d.window;
  const parts = [];
  if (cr) parts.push(`Over the ${wlabel} window ${coin} returned ${mkPct(cr[`ret_${d.window}`])}, versus a mixed picture across traditional markets.`);
  if (d.best && d.worst) parts.push(`Best performer: ${d.best.asset}; weakest: ${d.worst.asset}. ${coin} ranks #${d.coin_rank} of ${d.ranked_count}.`);
  const eq = (d.correlations || []).find((c) => c.asset === 'S&P 500');
  if (eq) parts.push(`${coin}'s 30-day correlation with the S&P 500 is ${eq.corr_30d} (${eq.label}) — ${Math.abs(eq.corr_30d || 0) > 0.5 ? 'currently moving closely with stocks (risk-on)' : 'fairly decoupled from stocks right now'}.`);
  return parts.join(' ');
}


function CrossMarketSection() {
  const symbol = React.useContext(SymbolContext);
  const [window, setWindow] = React.useState('1y');
  const [logScale, setLogScale] = React.useState(false);
  const [benchmark, setBenchmark] = React.useState('S&P 500');
  const [data, setData] = React.useState(null);
  const [status, setStatus] = React.useState('loading');

  React.useEffect(() => {
    let alive = true;
    setStatus('loading'); setData(null);
    const load = () => fetch(`${API_BASE}/v1/markets?symbol=${encodeURIComponent(symbol)}&window=${window}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((j) => { if (!alive) return; if (j.status === 'ready') { setData(j); setStatus('ready'); } else if (j.status === 'error') { setStatus('error'); } else { setStatus('computing'); } })
      .catch(() => { if (alive) setStatus('error'); });
    load();
    const id = setInterval(() => { setStatus((s) => { if (s !== 'ready') load(); return s; }); }, 5000);
    return () => { alive = false; clearInterval(id); };
  }, [symbol, window]);

  const colorFor = (asset) => MK_COLORS[(data ? data.assets.indexOf(asset) : 0) % MK_COLORS.length];
  const maxVol = data ? Math.max(1, ...data.table.map((t) => t.vol_annual || 0)) : 1;
  const winKey = `ret_${window}`;
  const benchmarks = (data && data.corr_benchmarks) || [];
  const activeBench = benchmarks.includes(benchmark) ? benchmark : (benchmarks[0] || 'S&P 500');
  const trend = (data && data.corr_trend_map && data.corr_trend_map[activeBench]) || (data && data.corr_trend) || [];

  return (
    <div className="space-y-6">
      <SectionHead icon={Globe} title="Cross-Market" blurb={sec('crossmarket').blurb} coin={symbol} />
      <AiReview text={reviewCrossMarket(data)} voice section="crossmarket" />

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Window</span>
        {MK_WINDOWS.map(([k, lbl]) => (
          <button key={k} onClick={() => setWindow(k)}
            className={`${TF_TOUCH} rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${window === k ? 'bg-sky-500/20 text-sky-200 ring-1 ring-sky-500/40' : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'}`}>{lbl}</button>
        ))}
      </div>

      {status !== 'ready' || !data ? (
        <Card className="border-0 bg-slate-900/60 p-10 text-center ring-1 ring-slate-800">
          <p className="text-sm text-slate-400">{status === 'error' ? 'Could not load market data. Retrying…' : `Loading ${(COMPARE_NAMES && COMPARE_NAMES[symbol]) || symbol} vs traditional markets…`}</p>
        </Card>
      ) : (
        <>
          <Card className="border-0 bg-slate-900/60 p-5 ring-1 ring-slate-800">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-bold text-white">Rebased performance (start = 100)</h3>
              <div className="flex items-center gap-2">
                <div className="flex overflow-hidden rounded-lg ring-1 ring-slate-700">
                  {[[false, 'Linear'], [true, 'Log']].map(([v, lbl]) => (
                    <button key={lbl} onClick={() => setLogScale(v)}
                      className={`px-2.5 py-1 text-[11px] font-semibold transition-colors ${logScale === v ? 'bg-sky-500/20 text-sky-200' : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'}`}>{lbl}</button>
                  ))}
                </div>
                <span className="hidden text-[11px] text-slate-500 sm:inline">as of {data.as_of} · {data.coin_name} highlighted</span>
              </div>
            </div>
            <div className="h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.series} margin={{ top: 6, right: 12, left: -14, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="date" stroke="#64748b" fontSize={10} minTickGap={40} />
                  <YAxis stroke="#64748b" fontSize={11} scale={logScale ? 'log' : 'linear'} domain={['auto', 'auto']} allowDataOverflow tickFormatter={(v) => Math.round(v)} />
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {!logScale && <ReferenceLine y={100} stroke="#475569" strokeDasharray="4 4" />}
                  {data.assets.map((a) => (
                    <Line key={a} type="monotone" dataKey={a} stroke={colorFor(a)} dot={false}
                      strokeWidth={a === data.coin_name ? 2.6 : 1.3} connectNulls />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card className="border-0 bg-slate-900/60 p-5 ring-1 ring-slate-800">
            <h3 className="mb-3 text-sm font-bold text-white">Returns by market</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] uppercase tracking-wider text-slate-500">
                    <th className="px-2 py-2 text-left">Market</th>
                    <th className="px-2 py-2 text-right">1W</th><th className="px-2 py-2 text-right">1M</th>
                    <th className="px-2 py-2 text-right">3M</th><th className="px-2 py-2 text-right">6M</th>
                    <th className="px-2 py-2 text-right">YTD</th><th className="px-2 py-2 text-right">1Y</th>
                    <th className="px-2 py-2 text-right">Ann. Vol</th>
                  </tr>
                </thead>
                <tbody>
                  {data.table.map((t) => (
                    <tr key={t.asset} className={`border-t border-slate-800/70 ${t.is_coin ? 'bg-sky-500/[0.06]' : ''}`}>
                      <td className="px-2 py-2 font-semibold text-slate-200">
                        <span className="mr-2 inline-block h-2 w-2 rounded-full align-middle" style={{ background: colorFor(t.asset) }} />
                        {t.asset}{t.is_coin && <span className="ml-1.5 rounded bg-sky-500/20 px-1.5 py-0.5 text-[9px] font-bold text-sky-300">YOU</span>}
                      </td>
                      <td className={`px-2 py-2 text-right ${mkPctColor(t.ret_1w)}`}>{mkPct(t.ret_1w)}</td>
                      <td className={`px-2 py-2 text-right ${mkPctColor(t.ret_1m)}`}>{mkPct(t.ret_1m)}</td>
                      <td className={`px-2 py-2 text-right ${mkPctColor(t.ret_3m)}`}>{mkPct(t.ret_3m)}</td>
                      <td className={`px-2 py-2 text-right ${mkPctColor(t.ret_6m)}`}>{mkPct(t.ret_6m)}</td>
                      <td className={`px-2 py-2 text-right ${mkPctColor(t.ret_ytd)}`}>{mkPct(t.ret_ytd)}</td>
                      <td className={`px-2 py-2 text-right ${mkPctColor(t.ret_1y)}`}>{mkPct(t.ret_1y)}</td>
                      <td className="px-2 py-2 text-right text-slate-300">{t.vol_annual != null ? `${t.vol_annual}%` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="border-0 bg-slate-900/60 p-5 ring-1 ring-slate-800">
              <TapInfo text={`How closely ${data.coin_name} moves with each market. +1 = moves together, 0 = unrelated, −1 = moves opposite. Beta shows how much ${data.coin_name} moves for a 1% move in that market.`} className="mb-3">
                <h3 className="pr-5 text-sm font-bold text-white">Correlation with {data.coin_name}</h3>
              </TapInfo>
              <div className="space-y-2">
                {data.correlations.map((c) => {
                  const v = c.corr_30d || 0;
                  const pos = v >= 0;
                  return (
                    <div key={c.asset} className="flex items-center gap-3">
                      <span className="w-28 shrink-0 truncate text-xs text-slate-300">{c.asset}</span>
                      <div className="relative h-2.5 flex-1 rounded-full bg-slate-800">
                        <div className="absolute left-1/2 top-0 h-full w-px bg-slate-600" />
                        <div className={`absolute top-0 h-full rounded-full ${pos ? 'bg-emerald-400/70' : 'bg-red-400/70'}`}
                          style={{ left: pos ? '50%' : `${50 - Math.abs(v) * 50}%`, width: `${Math.abs(v) * 50}%` }} />
                      </div>
                      <span className={`w-10 shrink-0 text-right text-xs font-semibold ${pos ? 'text-emerald-400' : 'text-red-400'}`}>{v}</span>
                      <span className="w-24 shrink-0 text-right text-[10px] text-slate-500">β {c.beta_30d ?? '—'}</span>
                    </div>
                  );
                })}
              </div>
              <p className="mt-3 text-[11px] text-slate-500">30-day correlation shown; β = 30-day beta. Positive = risk-on coupling with that market; near-zero or negative = decoupled.</p>
            </Card>

            <Card className="border-0 bg-slate-900/60 p-5 ring-1 ring-slate-800">
              <TapInfo text="Annualized volatility — how much each market swings over a year. Higher = bumpier. Crypto is typically far more volatile than equities." className="mb-3">
                <h3 className="pr-5 text-sm font-bold text-white">Volatility (annualized)</h3>
              </TapInfo>
              <div className="space-y-2">
                {[...data.table].filter((t) => t.vol_annual != null).sort((a, b) => b.vol_annual - a.vol_annual).map((t) => (
                  <div key={t.asset} className="flex items-center gap-3">
                    <span className="w-28 shrink-0 truncate text-xs text-slate-300">{t.asset}</span>
                    <div className="h-2.5 flex-1 rounded-full bg-slate-800">
                      <div className="h-full rounded-full" style={{ width: `${(t.vol_annual / maxVol) * 100}%`, background: colorFor(t.asset) }} />
                    </div>
                    <span className="w-12 shrink-0 text-right text-xs font-semibold text-slate-200">{t.vol_annual}%</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {trend && trend.length > 1 && (
            <Card className="border-0 bg-slate-900/60 p-5 ring-1 ring-slate-800">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <TapInfo text={`A rolling 30-day correlation between ${data.coin_name} and the chosen market over time. Above 0 = moving together (risk-on); near 0 or below = decoupled. The drift matters more than today's single number.`}>
                  <h3 className="pr-5 text-sm font-bold text-white">How {data.coin_name} tracks {activeBench} · 30-day rolling correlation</h3>
                </TapInfo>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Benchmark</span>
                  <select value={activeBench} onChange={(e) => setBenchmark(e.target.value)}
                    className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1 text-xs font-semibold text-slate-200 outline-none focus:border-sky-500/60">
                    {benchmarks.map((b) => <option key={b} value={b}>{b}</option>)}
                  </select>
                </div>
              </div>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trend} margin={{ top: 6, right: 12, left: -18, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="date" stroke="#64748b" fontSize={10} minTickGap={40} />
                    <YAxis stroke="#64748b" fontSize={11} domain={[-1, 1]} ticks={[-1, -0.5, 0, 0.5, 1]} />
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
                    <ReferenceLine y={0} stroke="#475569" strokeDasharray="4 4" />
                    <Line type="monotone" dataKey="corr" stroke={colorFor(activeBench)} strokeWidth={2} dot={false} name={`30d corr vs ${activeBench}`} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-[11px] text-slate-500">Latest: <b className="text-slate-300">{trend[trend.length - 1].corr}</b> vs {activeBench} · {trend.length} days shown. Rising = coupling; falling = decoupling.</p>
            </Card>
          )}

          {data.best && data.worst && (
            <Card className="border-0 bg-gradient-to-br from-slate-900 to-slate-900/60 p-5 ring-1 ring-slate-800">
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
                <span className="text-slate-400">Over the <b className="text-slate-200">{(MK_WINDOWS.find((w) => w[0] === window) || [])[1]}</b> window:</span>
                <span className="text-emerald-400">▲ Best: <b>{data.best.asset}</b> ({mkPct(data.best[winKey])})</span>
                <span className="text-red-400">▼ Weakest: <b>{data.worst.asset}</b> ({mkPct(data.worst[winKey])})</span>
                <span className="text-sky-300">{data.coin_name} ranks <b>#{data.coin_rank}</b> of {data.ranked_count}</span>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}


export default CrossMarketSection;
