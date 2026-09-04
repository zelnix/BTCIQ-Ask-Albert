'use client';

import React from 'react';
import {
  Radar, Waves, TrendingUp, TrendingDown, Activity, Gauge, ShieldAlert, Bell, Loader2,
  RefreshCw, Check, X, Zap, Droplet, Flame, ArrowUpRight, ArrowDownRight, Minus,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { API_BASE } from '../lib/api';
import { SectionHead } from './shared';

const SIGNAL_META = {
  gmma_crossover: { label: 'GMMA Trend Crossover', icon: Waves, desc: 'Fast EMAs (3–15) fully cross the slow EMAs (30–60) — a macro shift between accumulation and expansion.' },
  dip_buy: { label: 'Trend Pullback / Dip-Buy', icon: TrendingUp, desc: 'In an expanded bull ribbon, price taps the slow ribbon and prints a green recovery candle — a value entry.' },
  squeeze: { label: 'Volatility Squeeze', icon: Activity, desc: 'Bollinger Band width compresses to a multi-week low — the market is coiling for an expansion.' },
  rsi_exhaustion: { label: 'RSI Exhaustion', icon: Gauge, desc: 'RSI(14) drops below the oversold or spikes above the overbought threshold — a reality check on hot/cold trends.' },
};
const FILTER_META = {
  volume: { label: 'Volume Spike Confirmation', icon: Zap, desc: 'Only confirm crossover alerts when volume ≥ the chosen multiple of the 20-day average — kills low-liquidity fakeouts.' },
  funding: { label: 'Funding Rate Filter', icon: Flame, desc: 'Suppress LONG alerts when perp funding is aggressively positive (a leverage flush is likely).' },
  netflow: { label: 'Exchange Netflow (BTC)', icon: Droplet, desc: 'Large BTC exchange inflows flag sell-pressure and override short-term buys. BTC-only for now.' },
  fng: { label: 'Fear & Greed', icon: Gauge, desc: 'Fade the crowd — suppress longs at extreme greed; treat extreme fear as a high-conviction accumulation window.' },
};

function Toggle({ on, onClick }) {
  return (
    <button onClick={onClick}
      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${on ? 'bg-emerald-500' : 'bg-slate-600'}`}>
      <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${on ? 'translate-x-4' : 'translate-x-0.5'}`} />
    </button>
  );
}

const stateBadge = (s) => s === 'bull' ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
  : s === 'bear' ? 'border-red-500/40 bg-red-500/10 text-red-300' : 'border-slate-600 bg-slate-800/60 text-slate-300';

function Readout({ label, value, sub, tone }) {
  const c = tone === 'good' ? 'text-emerald-400' : tone === 'bad' ? 'text-red-400' : tone === 'warn' ? 'text-amber-400' : 'text-slate-100';
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-2.5">
      <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`text-sm font-bold ${c}`}>{value}</p>
      {sub && <p className="text-[10px] text-slate-500">{sub}</p>}
    </div>
  );
}

export default function AlertEngineSection() {
  const [cfg, setCfg] = React.useState(null);
  const [coin, setCoin] = React.useState('BTC');
  const [readings, setReadings] = React.useState(null);
  const [loadingR, setLoadingR] = React.useState(false);
  const [scanning, setScanning] = React.useState(false);
  const [recent, setRecent] = React.useState([]);

  const loadConfig = React.useCallback(async () => {
    try {
      const j = await (await fetch(`${API_BASE}/v1/alert-engine/config`)).json();
      if (j && j.settings) setCfg(j);
    } catch (e) { /* noop */ }
  }, []);
  const loadReadings = React.useCallback(async (sym) => {
    setLoadingR(true);
    try {
      const j = await (await fetch(`${API_BASE}/v1/alert-engine/readings?symbol=${sym}`, { cache: 'no-store' })).json();
      setReadings(j);
    } catch (e) { setReadings(null); } finally { setLoadingR(false); }
  }, []);
  const loadRecent = React.useCallback(async () => {
    try {
      const j = await (await fetch(`${API_BASE}/v1/alert-engine/recent?limit=20`)).json();
      setRecent(j.alerts || []);
    } catch (e) { /* noop */ }
  }, []);

  React.useEffect(() => { loadConfig(); loadRecent(); }, [loadConfig, loadRecent]);
  React.useEffect(() => { loadReadings(coin); }, [coin, loadReadings]);

  const settings = cfg?.settings;
  const save = async (patch) => {
    // optimistic merge
    setCfg((c) => {
      const s = { ...c.settings };
      for (const k of Object.keys(patch)) s[k] = (typeof patch[k] === 'object' && !Array.isArray(patch[k])) ? { ...s[k], ...patch[k] } : patch[k];
      return { ...c, settings: s };
    });
    try {
      const j = await (await fetch(`${API_BASE}/v1/alert-engine/config`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ settings: patch }),
      })).json();
      if (j && j.settings) setCfg((c) => ({ ...c, settings: j.settings }));
    } catch (e) { /* noop */ }
  };

  const scanNow = async () => {
    setScanning(true);
    try {
      await fetch(`${API_BASE}/v1/alert-engine/scan`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol: coin }) });
      await loadReadings(coin); await loadRecent();
    } catch (e) { /* noop */ } finally { setScanning(false); }
  };

  if (!settings) {
    return (
      <div className="space-y-4">
        <SectionHead icon={Radar} title="Alert Engine" blurb="Daily technical signal detectors with smart context filters." />
        <Card className="border-0 bg-slate-900 p-8 text-center ring-1 ring-slate-800"><Loader2 className="mx-auto h-6 w-6 animate-spin text-slate-500" /></Card>
      </div>
    );
  }

  const r = readings?.readings;
  const f = readings?.filters;
  const cands = readings?.candidates || [];
  const inWatch = (settings.watchlist || []).includes(coin);

  return (
    <div className="space-y-4">
      <SectionHead icon={Radar} title="Alert Engine"
        blurb="Daily (1D) technical signal detectors — GMMA crossovers, trend dip-buys, volatility squeezes and RSI exhaustion — refined by volume, funding, exchange-netflow and Fear & Greed filters. Albert scans your watchlist hourly and fires in-app alerts when a signal triggers." />

      {/* Master enable */}
      <Card className="flex items-center gap-3 border-0 bg-slate-900/60 p-4 ring-1 ring-slate-800">
        <span className={`flex h-9 w-9 items-center justify-center rounded-full ${settings.enabled ? 'bg-emerald-500/15 text-emerald-400' : 'bg-slate-800 text-slate-500'}`}><Radar className="h-4 w-4" /></span>
        <div className="flex-1">
          <p className="text-sm font-bold text-white">Engine {settings.enabled ? 'active' : 'paused'}</p>
          <p className="text-[11px] text-slate-400">Scanning {settings.watchlist?.length || 0} coins on the Daily timeframe, hourly.</p>
        </div>
        <Toggle on={settings.enabled} onClick={() => save({ enabled: !settings.enabled })} />
      </Card>

      {/* Live readings */}
      <Card className="border-0 bg-slate-900/60 p-4 ring-1 ring-slate-800">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-bold text-white">Live readings</h3>
          <select value={coin} onChange={(e) => setCoin(e.target.value)}
            className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-[13px] font-semibold text-slate-100 focus:border-sky-500/60 focus:outline-none">
            {(cfg.coins || []).map((c) => <option key={c.symbol} value={c.symbol}>{c.symbol} · {c.name}</option>)}
          </select>
          {!inWatch && <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-300">not in watchlist</span>}
          <Button onClick={scanNow} disabled={scanning} size="sm" className="ml-auto h-7 gap-1 bg-sky-500 text-white hover:bg-sky-400">
            {scanning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}Scan now
          </Button>
        </div>
        {loadingR ? (
          <div className="py-6 text-center"><Loader2 className="mx-auto h-5 w-5 animate-spin text-slate-500" /></div>
        ) : r ? (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-2.5">
                <p className="text-[10px] uppercase tracking-wide text-slate-500">GMMA</p>
                <span className={`mt-0.5 inline-block rounded-full border px-2 py-0.5 text-[11px] font-bold capitalize ${stateBadge(r.gmma_state)}`}>{r.gmma_state}</span>
                <p className="text-[10px] text-slate-500">spread {r.slow_spread_pct}%</p>
              </div>
              <Readout label="RSI (14)" value={r.rsi} tone={r.rsi_overbought ? 'bad' : r.rsi_oversold ? 'warn' : 'neutral'} sub={r.rsi_overbought ? 'overbought' : r.rsi_oversold ? 'oversold' : 'neutral'} />
              <Readout label="BB width" value={`${r.bb_width_pct}%`} tone={r.squeeze ? 'warn' : 'neutral'} sub={`${r.bb_width_percentile}th pctile${r.squeeze ? ' · squeeze' : ''}`} />
              <Readout label="Volume" value={r.vol_ratio != null ? `${r.vol_ratio}×` : '—'} tone={r.vol_ratio >= (settings.volume_mult || 1.5) ? 'good' : 'neutral'} sub="vs 20-day avg" />
              <Readout label="Funding" value={f?.funding != null ? `${f.funding}%` : '—'} tone={f?.funding_suppress_long ? 'bad' : 'neutral'} sub={f?.funding_suppress_long ? 'hot — longs off' : 'normal'} />
              <Readout label="Fear & Greed" value={f?.fng_value ?? '—'} tone={f?.fng_suppress_long ? 'bad' : f?.fng_accumulate ? 'good' : 'neutral'} sub={f?.fng_label || ''} />
            </div>
            {f?.netflow_available && (
              <div className="mt-2 flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/50 px-2.5 py-2 text-[12px] text-slate-300">
                <Droplet className={`h-3.5 w-3.5 ${f.netflow_warning ? 'text-red-400' : 'text-slate-500'}`} />
                BTC exchange netflow (7d): <span className={`font-semibold ${f.netflow_warning ? 'text-red-300' : 'text-slate-200'}`}>{f.netflow_net7d > 0 ? '+' : ''}{Math.round(f.netflow_net7d).toLocaleString()} BTC</span>
                {f.netflow_warning && <span className="text-red-300">— inflows overriding short-term buys</span>}
              </div>
            )}
            <p className="mt-3 mb-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-500">Signals on this candle ({r.candle_date})</p>
            {cands.length ? (
              <div className="space-y-1.5">
                {cands.map((c, i) => (
                  <div key={i} className={`flex items-start gap-2 rounded-lg border p-2.5 ${c.blocked?.length ? 'border-slate-800 bg-slate-900/40 opacity-70' : c.direction === 'short' ? 'border-red-500/40 bg-red-500/5' : c.direction === 'long' ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-sky-500/40 bg-sky-500/5'}`}>
                    <span className="mt-0.5">{c.direction === 'long' ? <ArrowUpRight className="h-4 w-4 text-emerald-400" /> : c.direction === 'short' ? <ArrowDownRight className="h-4 w-4 text-red-400" /> : <Minus className="h-4 w-4 text-sky-400" />}</span>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-semibold text-slate-100">{c.title}</p>
                      <p className="text-[12px] leading-snug text-slate-400">{c.message}</p>
                      {c.blocked?.length ? <p className="mt-1 text-[11px] font-medium text-amber-300">Suppressed: {c.blocked.join(' · ')}</p> : null}
                    </div>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${c.blocked?.length ? 'bg-slate-800 text-slate-500' : 'bg-emerald-500/20 text-emerald-300'}`}>{c.blocked?.length ? 'BLOCKED' : 'WOULD FIRE'}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-3 text-center text-[12px] text-slate-500">No signals triggered on {coin}&apos;s latest daily candle. Albert is watching.</p>
            )}
          </>
        ) : (
          <p className="py-4 text-center text-[12px] text-slate-500">Couldn&apos;t load {coin} data. Try Scan now.</p>
        )}
      </Card>

      {/* Signals config */}
      <Card className="border-0 bg-slate-900/60 p-4 ring-1 ring-slate-800">
        <h3 className="mb-2 text-sm font-bold text-white">Signal detectors</h3>
        <div className="space-y-2">
          {Object.entries(SIGNAL_META).map(([key, m]) => {
            const Icon = m.icon;
            const on = !!settings.signals?.[key];
            return (
              <div key={key} className="flex items-start gap-3 rounded-lg border border-slate-800 bg-slate-900/40 p-3">
                <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${on ? 'bg-sky-500/15 text-sky-300' : 'bg-slate-800 text-slate-500'}`}><Icon className="h-3.5 w-3.5" /></span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-semibold text-slate-100">{m.label}</p>
                  <p className="text-[11px] leading-snug text-slate-400">{m.desc}</p>
                  {key === 'rsi_exhaustion' && on && (
                    <div className="mt-1.5 flex items-center gap-2 text-[11px] text-slate-400">
                      <span>Oversold &lt;</span>
                      <input type="number" value={settings.rsi_low} onChange={(e) => save({ rsi_low: Number(e.target.value) })} className="w-14 rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-slate-100" />
                      <span>Overbought &gt;</span>
                      <input type="number" value={settings.rsi_high} onChange={(e) => save({ rsi_high: Number(e.target.value) })} className="w-14 rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-slate-100" />
                    </div>
                  )}
                </div>
                <Toggle on={on} onClick={() => save({ signals: { [key]: !on } })} />
              </div>
            );
          })}
        </div>
      </Card>

      {/* Filters config */}
      <Card className="border-0 bg-slate-900/60 p-4 ring-1 ring-slate-800">
        <h3 className="mb-2 text-sm font-bold text-white">Context filters</h3>
        <div className="space-y-2">
          {Object.entries(FILTER_META).map(([key, m]) => {
            const Icon = m.icon;
            const on = !!settings.filters?.[key];
            return (
              <div key={key} className="flex items-start gap-3 rounded-lg border border-slate-800 bg-slate-900/40 p-3">
                <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${on ? 'bg-violet-500/15 text-violet-300' : 'bg-slate-800 text-slate-500'}`}><Icon className="h-3.5 w-3.5" /></span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-semibold text-slate-100">{m.label}</p>
                  <p className="text-[11px] leading-snug text-slate-400">{m.desc}</p>
                  {key === 'volume' && on && (
                    <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-slate-400">
                      <span>Require volume ≥</span>
                      {[1.5, 2].map((v) => (
                        <button key={v} onClick={() => save({ volume_mult: v })}
                          className={`rounded px-2 py-0.5 font-semibold ${settings.volume_mult === v ? 'bg-sky-500/20 text-sky-200' : 'bg-slate-800 text-slate-400'}`}>{v}×</button>
                      ))}
                      <span>the 20-day avg</span>
                    </div>
                  )}
                  {key === 'funding' && on && (
                    <div className="mt-1.5 flex items-center gap-2 text-[11px] text-slate-400">
                      <span>Suppress longs when funding &gt;</span>
                      <input type="number" step="0.01" value={settings.funding_threshold} onChange={(e) => save({ funding_threshold: Number(e.target.value) })} className="w-16 rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-slate-100" />
                      <span>%</span>
                    </div>
                  )}
                  {key === 'fng' && on && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                      <span>Greed ≥</span>
                      <input type="number" value={settings.greed_threshold} onChange={(e) => save({ greed_threshold: Number(e.target.value) })} className="w-14 rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-slate-100" />
                      <span>· Fear ≤</span>
                      <input type="number" value={settings.fear_threshold} onChange={(e) => save({ fear_threshold: Number(e.target.value) })} className="w-14 rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-slate-100" />
                    </div>
                  )}
                </div>
                <Toggle on={on} onClick={() => save({ filters: { [key]: !on } })} />
              </div>
            );
          })}
        </div>
      </Card>

      {/* Watchlist */}
      <Card className="border-0 bg-slate-900/60 p-4 ring-1 ring-slate-800">
        <div className="mb-2 flex items-center gap-2">
          <h3 className="text-sm font-bold text-white">Watchlist</h3>
          <span className="text-[11px] text-slate-500">{settings.watchlist?.length || 0} of {cfg.coins?.length} coins</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(cfg.coins || []).map((c) => {
            const on = (settings.watchlist || []).includes(c.symbol);
            return (
              <button key={c.symbol}
                onClick={() => save({ watchlist: on ? settings.watchlist.filter((x) => x !== c.symbol) : [...settings.watchlist, c.symbol] })}
                className={`rounded-full border px-2.5 py-1 text-[12px] font-semibold transition-colors ${on ? 'border-sky-500/50 bg-sky-500/15 text-sky-200' : 'border-slate-700 bg-slate-800/50 text-slate-400 hover:text-white'}`}>
                {on && <Check className="mr-1 inline h-3 w-3" />}{c.symbol}
              </button>
            );
          })}
        </div>
      </Card>

      {/* Recent fires */}
      <Card className="border-0 bg-slate-900/60 p-4 ring-1 ring-slate-800">
        <div className="mb-2 flex items-center gap-2">
          <Bell className="h-4 w-4 text-slate-400" />
          <h3 className="text-sm font-bold text-white">Recent signal alerts</h3>
        </div>
        {recent.length ? (
          <div className="space-y-1.5">
            {recent.map((a) => (
              <div key={a.id} className="flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-900/40 p-2.5">
                <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${a.severity === 'high' ? 'bg-red-400' : a.severity === 'medium' ? 'bg-amber-400' : 'bg-sky-400'}`} />
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-semibold text-slate-100">{a.title}</p>
                  <p className="text-[11px] leading-snug text-slate-400">{a.message}</p>
                </div>
                <span className="shrink-0 text-[10px] text-slate-500">{(() => { try { return new Date(a.ts + (/[zZ]$/.test(a.ts) ? '' : 'Z')).toLocaleString(); } catch { return ''; } })()}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-4 text-center text-[12px] text-slate-500">No signal alerts fired yet. When a detector triggers on a daily candle, it&apos;ll show here and in your notification bell.</p>
        )}
      </Card>
    </div>
  );
}
