'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  ResponsiveContainer, ComposedChart, Line, Area, Bar, BarChart,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell,
} from 'recharts';
import {
  TrendingUp, TrendingDown, RefreshCw, Activity, Gauge,
  Waves, BarChart3, ArrowUpRight, ArrowDownRight, Cpu, Database,
  Trophy, Radio, History, Check, X,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

const CAT_COLORS = {
  Trend: 'text-sky-400 bg-sky-500/10 border-sky-500/30',
  Momentum: 'text-violet-400 bg-violet-500/10 border-violet-500/30',
  Volatility: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  Volume: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
};
const BAR_COLORS = ['#38bdf8', '#a78bfa', '#fbbf24', '#34d399', '#f472b6', '#60a5fa', '#f87171', '#4ade80'];

const fmtUsd = (v) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);
const fmtPct = (v) => `${Number(v).toFixed(1)}%`;

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/95 px-3 py-2 shadow-xl">
      <p className="mb-1 text-xs font-bold text-slate-400">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="text-xs" style={{ color: p.color }}>
          {p.name}: {p.name === 'BTC Price' ? fmtUsd(p.value) : fmtPct(p.value)}
        </p>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [ticker, setTicker] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/dashboard', { cache: 'no-store' });
      const json = await res.json();
      if (json.status === 'ready') {
        setData(json);
        setStatus('ready');
        setRefreshing(false);
      } else if (json.status === 'error') {
        setError(json.error || 'Unknown error');
        setStatus('error');
      } else {
        setStatus('computing');
      }
    } catch (e) {
      setError(String(e));
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(() => {
      setStatus((s) => {
        if (s !== 'ready') load();
        return s;
      });
    }, 4000);
    return () => clearInterval(id);
  }, [load]);

  // Live ticker polling (every 10s) + dashboard auto-refresh (every 60s)
  useEffect(() => {
    let alive = true;
    const loadTicker = async () => {
      try {
        const r = await fetch('/api/v1/ticker', { cache: 'no-store' });
        const j = await r.json();
        if (alive && j && j.price) setTicker(j);
      } catch (e) { /* noop */ }
    };
    loadTicker();
    const t = setInterval(loadTicker, 10000);
    const dref = setInterval(() => load(), 60000);
    return () => { alive = false; clearInterval(t); clearInterval(dref); };
  }, [load]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetch('/api/v1/refresh', { method: 'POST' });
    setTimeout(load, 1500);
    const id = setInterval(load, 4000);
    setTimeout(() => clearInterval(id), 60000);
  };

  if (status === 'loading' || status === 'computing') {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-slate-950 px-6">
        <div className="relative">
          <div className="h-16 w-16 animate-spin rounded-full border-4 border-slate-800 border-t-sky-400" />
          <Cpu className="absolute inset-0 m-auto h-6 w-6 text-sky-400" />
        </div>
        <div className="text-center">
          <h2 className="text-lg font-semibold text-slate-100">Training model on real BTC data…</h2>
          <p className="mt-1 text-sm text-slate-400">
            Fetching 720 daily candles · engineering features · walk-forward backtesting
          </p>
        </div>
      </main>
    );
  }

  if (status === 'error') {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-950 px-6">
        <div className="rounded-full bg-red-500/10 p-4"><Activity className="h-8 w-8 text-red-400" /></div>
        <h2 className="text-lg font-semibold text-slate-100">Engine error</h2>
        <p className="max-w-md text-center text-sm text-slate-400">{error}</p>
        <Button onClick={handleRefresh} className="bg-sky-500 hover:bg-sky-400">Retry</Button>
      </main>
    );
  }

  const d = data;
  const isUp = d.signal === 'UP';

  return (
    <main className="min-h-screen bg-slate-950 px-4 py-8 md:px-8">
      <div className="mx-auto max-w-6xl space-y-6">
        {/* Header */}
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-5">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-gradient-to-br from-sky-500 to-violet-600 p-2.5">
              <Activity className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-white">BTC Quant AI</h1>
              <p className="text-sm text-slate-400">RandomForest next-day directional signal · real market data</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant="outline" className="gap-1.5 border-slate-700 text-slate-300">
              <Database className="h-3.5 w-3.5" /> {d.data_source} · {d.pair}
            </Badge>
            <Button onClick={handleRefresh} disabled={refreshing} size="sm"
              className="gap-2 bg-slate-800 text-slate-100 hover:bg-slate-700">
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
              {refreshing ? 'Retraining' : 'Retrain'}
            </Button>
          </div>
        </header>

        {/* Top stat row */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          {/* Signal card */}
          <Card className={`col-span-1 border-0 p-5 md:col-span-2 ${isUp ? 'bg-gradient-to-br from-emerald-500/15 to-slate-900' : 'bg-gradient-to-br from-red-500/15 to-slate-900'} ring-1 ${isUp ? 'ring-emerald-500/30' : 'ring-red-500/30'}`}>
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Next-Day Signal · as of {d.as_of}</p>
                <div className="mt-2 flex items-center gap-3">
                  {isUp ? <TrendingUp className="h-10 w-10 text-emerald-400" /> : <TrendingDown className="h-10 w-10 text-red-400" />}
                  <span className={`text-4xl font-black ${isUp ? 'text-emerald-400' : 'text-red-400'}`}>{d.signal}</span>
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Confidence</p>
                <p className="text-3xl font-bold text-white">{d.confidence}%</p>
              </div>
            </div>
            <div className="mt-4 flex gap-2">
              <div className="flex-1 rounded-lg bg-slate-900/60 p-2 text-center">
                <p className="text-[11px] text-slate-400">P(Up)</p>
                <p className="text-sm font-bold text-emerald-400">{d.prob_up}%</p>
              </div>
              <div className="flex-1 rounded-lg bg-slate-900/60 p-2 text-center">
                <p className="text-[11px] text-slate-400">P(Down)</p>
                <p className="text-sm font-bold text-red-400">{d.prob_down}%</p>
              </div>
            </div>
          </Card>

          <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">BTC Live Price</p>
              <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-400">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
                </span>
                LIVE
              </span>
            </div>
            <p className="mt-2 text-2xl font-bold text-white">{fmtUsd(ticker?.price ?? d.last_close)}</p>
            {(() => {
              const ch = ticker?.change24h ?? d.day_change_pct;
              return (
                <p className={`mt-1 flex items-center gap-1 text-sm font-semibold ${ch >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {ch >= 0 ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
                  {ch}% (24h){ticker?.source ? ` \u00b7 ${ticker.source}` : ''}
                </p>
              );
            })()}
          </Card>

          <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Backtest Accuracy</p>
            <p className="mt-2 text-2xl font-bold text-sky-400">{d.overall_accuracy}%</p>
            <p className="mt-1 text-sm text-slate-400">CV mean {d.cv_mean}% · {d.n_samples} days</p>
          </Card>
        </div>

        {/* Success rate chart */}
        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <div className="mb-4">
            <h2 className="text-lg font-semibold text-slate-100">AI Model Performance History</h2>
            <p className="text-sm text-slate-400">30-day rolling accuracy vs BTC spot price · {d.first_date} → {d.as_of}</p>
          </div>
          <div className="h-[420px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={d.performance} margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
                <defs>
                  <linearGradient id="btcFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#94a3b8" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#94a3b8" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickLine={false} minTickGap={40} />
                <YAxis yAxisId="left" orientation="left" stroke="#94a3b8" fontSize={11}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} tickLine={false} domain={['auto', 'auto']} />
                <YAxis yAxisId="right" orientation="right" stroke="#38bdf8" fontSize={11}
                  tickFormatter={(v) => `${v}%`} tickLine={false} domain={[30, 90]} />
                <Tooltip content={<ChartTooltip />} />
                <Legend verticalAlign="top" height={30} wrapperStyle={{ fontSize: 13 }} />
                <Area yAxisId="left" name="BTC Price" type="monotone" dataKey="btcPrice"
                  stroke="#94a3b8" strokeWidth={1.5} fill="url(#btcFill)" />
                <Line yAxisId="right" name="AI Accuracy" type="monotone" dataKey="aiAccuracy"
                  stroke="#38bdf8" strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Scoreboard + Trade Log */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card className="border-0 bg-gradient-to-br from-sky-500/10 to-slate-900 p-6 ring-1 ring-slate-800 lg:col-span-1">
            <div className="mb-2 flex items-center gap-2">
              <Trophy className="h-5 w-5 text-amber-400" />
              <h2 className="text-lg font-semibold text-slate-100">AI Scoreboard</h2>
            </div>
            <p className="text-xs text-slate-400">Real out-of-sample record · {d.scoreboard.total} predictions graded</p>
            <div className="mt-3 flex items-end gap-2">
              <span className="text-5xl font-black text-sky-400">{d.scoreboard.winRate}%</span>
              <span className="mb-1 text-sm text-slate-400">win rate</span>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg bg-emerald-500/10 p-2">
                <p className="text-[11px] text-slate-400">Wins</p>
                <p className="text-lg font-bold text-emerald-400">{d.scoreboard.wins}</p>
              </div>
              <div className="rounded-lg bg-red-500/10 p-2">
                <p className="text-[11px] text-slate-400">Losses</p>
                <p className="text-lg font-bold text-red-400">{d.scoreboard.losses}</p>
              </div>
              <div className="rounded-lg bg-slate-800/60 p-2">
                <p className="text-[11px] text-slate-400">Streak</p>
                <p className={`text-lg font-bold ${d.scoreboard.currentStreak >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {d.scoreboard.currentStreak >= 0 ? `${d.scoreboard.currentStreak}W` : `${Math.abs(d.scoreboard.currentStreak)}L`}
                </p>
              </div>
            </div>
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
              <Radio className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
              <div className="text-xs text-slate-400">
                <span className="font-semibold text-slate-200">Live forward record:</span> {d.live_record.tracked} tracked · {d.live_record.resolved} resolved
                {d.live_record.winRate != null ? ` \u00b7 ${d.live_record.winRate}% hit` : ' \u00b7 grading begins on the next daily candle'}
              </div>
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
              Next prediction target: <span className="font-mono text-slate-400">{d.predict_for_date}</span>
            </p>
          </Card>

          <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800 lg:col-span-2">
            <div className="mb-3 flex items-center gap-2">
              <History className="h-5 w-5 text-slate-400" />
              <h2 className="text-lg font-semibold text-slate-100">Trade Log</h2>
              <span className="text-sm text-slate-500">last {d.trades.length} graded predictions</span>
            </div>
            <div className="max-h-[320px] overflow-y-auto pr-1">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-slate-900 text-left text-xs uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="py-2">Date</th>
                    <th className="py-2">Signal</th>
                    <th className="py-2 text-right">Conf.</th>
                    <th className="hidden py-2 text-right sm:table-cell">Close → Next</th>
                    <th className="py-2 text-right">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {d.trades.map((t, i) => (
                    <tr key={i} className="border-t border-slate-800/60">
                      <td className="py-2 font-mono text-xs text-slate-400">{t.date}</td>
                      <td className="py-2">
                        <span className={`inline-flex items-center gap-1 font-semibold ${t.signal === 'UP' ? 'text-emerald-400' : 'text-red-400'}`}>
                          {t.signal === 'UP' ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}{t.signal}
                        </span>
                      </td>
                      <td className="py-2 text-right font-mono text-slate-300">{t.confidence}%</td>
                      <td className="hidden py-2 text-right font-mono text-xs text-slate-400 sm:table-cell">
                        {fmtUsd(t.close)} → {fmtUsd(t.nextClose)}
                      </td>
                      <td className="py-2 text-right">
                        {t.correct
                          ? <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-bold text-emerald-400"><Check className="h-3 w-3" />WIN</span>
                          : <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-bold text-red-400"><X className="h-3 w-3" />LOSS</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        {/* Features + importance */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
            <div className="mb-4 flex items-center gap-2">
              <Gauge className="h-5 w-5 text-slate-400" />
              <h2 className="text-lg font-semibold text-slate-100">Live Feature Matrix</h2>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {d.features.map((f) => (
                <div key={f.feature} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-400">{f.label}</span>
                    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${CAT_COLORS[f.category]}`}>{f.category}</span>
                  </div>
                  <p className="mt-1.5 text-xl font-bold text-white">{f.value}<span className="ml-0.5 text-sm text-slate-500">{f.unit}</span></p>
                </div>
              ))}
            </div>
          </Card>

          <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
            <div className="mb-4 flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-slate-400" />
              <h2 className="text-lg font-semibold text-slate-100">Feature Importance</h2>
            </div>
            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={d.importances} layout="vertical" margin={{ left: 20, right: 20 }}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" stroke="#64748b" fontSize={11} tickFormatter={(v) => `${v}%`} />
                  <YAxis type="category" dataKey="label" stroke="#94a3b8" fontSize={11} width={110} tickLine={false} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: '#1e293b55' }} />
                  <Bar dataKey="importance" name="Importance" radius={[0, 4, 4, 0]}>
                    {d.importances.map((_, i) => <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>

        {/* CV folds */}
        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <div className="mb-4 flex items-center gap-2">
            <Waves className="h-5 w-5 text-slate-400" />
            <h2 className="text-lg font-semibold text-slate-100">TimeSeriesSplit Cross-Validation</h2>
            <span className="text-sm text-slate-500">(no future leakage)</span>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {d.cv_folds.map((f) => (
              <div key={f.fold} className="rounded-lg border border-slate-800 bg-slate-950/50 p-4 text-center">
                <p className="text-xs text-slate-400">Fold {f.fold}</p>
                <p className="mt-1 text-2xl font-bold text-sky-400">{f.accuracy}%</p>
                <p className="mt-1 text-[11px] text-slate-500">{f.testSize} test days</p>
              </div>
            ))}
          </div>
        </Card>

        <footer className="pb-6 pt-2 text-center text-xs text-slate-600">
          Educational research tool · not financial advice · real data via {d.data_source}
        </footer>
      </div>
    </main>
  );
}
