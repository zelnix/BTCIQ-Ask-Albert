'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  ResponsiveContainer, ComposedChart, Line, LineChart, Area, Bar, BarChart,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell,
  ScatterChart, Scatter, ReferenceLine, ZAxis,
} from 'recharts';
import {
  TrendingUp, TrendingDown, RefreshCw, Activity, Gauge, Waves, BarChart3,
  ArrowUpRight, ArrowDownRight, Cpu, Database, Trophy, Radio, History,
  Check, X, LayoutDashboard, Target, FlaskConical, Bell, MessageCircle,
  Sparkles, Info, Lock, Compass, CandlestickChart, Layers, Landmark, Globe, Newspaper,
  Brain, Send, ShieldAlert, Scale, CalendarClock, ClipboardList, ShieldCheck,
  Volume2, VolumeX, Maximize2, Minimize2, SlidersHorizontal, Magnet, Plus, Clock,
  ChevronDown, Coins, Fish,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

/* ------------------------------ helpers ------------------------------ */
const fmtUsd = (v) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v ?? 0);
const fmtAud = (v) => 'A$' + new Intl.NumberFormat('en-AU', { maximumFractionDigits: 0 }).format(v ?? 0);
const fmtPct = (v) => `${Number(v).toFixed(1)}%`;

// Real coin logo (keyless jsDelivr CDN). Falls back to a text badge if the image is missing.
function CoinIcon({ symbol, size = 24, className = '' }) {
  const [err, setErr] = React.useState(false);
  const sym = (symbol || '').toUpperCase();
  React.useEffect(() => { setErr(false); }, [symbol]);
  if (err || !symbol) {
    return (
      <span className={`flex items-center justify-center rounded-full bg-gradient-to-br from-amber-400/30 to-sky-500/30 font-black text-sky-200 ring-1 ring-sky-500/40 ${className}`} style={{ width: size, height: size, fontSize: size * 0.36 }}>{sym.slice(0, 3)}</span>
    );
  }
  return (
    <img src={`https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/${sym.toLowerCase()}.png`} alt={sym} onError={() => setErr(true)} className={`rounded-full ${className}`} style={{ width: size, height: size }} />
  );
}

const CAT_COLORS = {
  Trend: 'text-sky-400 bg-sky-500/10 border-sky-500/30',
  Momentum: 'text-violet-400 bg-violet-500/10 border-violet-500/30',
  Volatility: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  Volume: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
};
const BAR_COLORS = ['#38bdf8', '#a78bfa', '#fbbf24', '#34d399', '#f472b6', '#60a5fa', '#f87171', '#4ade80'];

const scoreColor = (s) =>
  s >= 60 ? '#34d399' : s >= 55 ? '#a3e635' : s > 45 ? '#fbbf24' : s > 40 ? '#fb923c' : '#f87171';
const signalText = (w) =>
  w === 'Bullish' || w === 'UP' ? 'text-emerald-400'
    : w === 'Bearish' || w === 'DOWN' ? 'text-red-400' : 'text-slate-300';

const SECTIONS = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard,
    blurb: 'Your 10-second snapshot of Bitcoin right now: the price, the market "mood", one simple score, the near-term odds, how risky things are and how sure the model is. Start here.' },
  { id: 'forecasts', label: 'Forecasts', icon: Target,
    blurb: 'BitMarkAI’s probability-based price forecasts from 1 week to 5 years — always shown as odds and price ranges (bull / base / bear), never a single guaranteed number. Longer horizons show wider uncertainty.' },
  { id: 'compare', label: 'Compare Coins', icon: Scale,
    blurb: 'Run the same quant engine across Bitcoin, Ethereum and Solana side by side — score, market mood, near-term odds and key levels — so you can see how the majors stack up. Each coin computes its own model on first view, then caches.' },
  { id: 'market-intel', label: 'Market Intelligence', icon: BarChart3,
    blurb: 'The technical picture behind the score: chart structure and key levels, where Bitcoin sits in its 4-year cycle, and the raw indicators the model reads.' },
  { id: 'crossmarket', label: 'Cross-Market', icon: Globe,
    blurb: 'How this coin stacks up against traditional markets — S&P 500, Nasdaq, Dow, Nikkei, European indices, Gold and the US Dollar. See rebased performance, returns, correlation (is crypto moving with stocks or breaking away?) and volatility.' },
  { id: 'analogs', label: 'Happening Again', icon: History,
    blurb: "Finds which past Bitcoin trend episode today's conditions most resemble — using macro rates, the US dollar, equity & gold correlation, volatility, drawdown, momentum and halving-cycle position — then shows what happened next. Adjust the sliders to weight what matters to you. Educational pattern-matching, not a prediction." },
  { id: 'smartmoney', label: 'Smart Money', icon: Waves,
    blurb: 'On-chain "smart money" behaviour — valuation (MVRV, SOPR), network activity, holder accumulation and sentiment. Powered by real on-chain data (BGeometrics, blockchain.com, Glassnode) and Fear & Greed.' },
  { id: 'whales', label: 'Whale Watch', icon: Fish,
    blurb: 'Live balances of the largest, publicly-labeled Bitcoin wallets — major exchanges, ETF/treasury custody, governments and famous whales. Track who is accumulating or distributing, with balances fetched live on-chain. Names are curated from public labels.' },
  { id: 'institutional', label: 'Institutional & Derivatives', icon: Landmark,
    blurb: 'Institutional & derivatives footprint — futures open interest, funding, long/short positioning and taker flow (live via OKX), plus REAL US spot Bitcoin ETF net flows (live via Farside/bitbo).' },
  { id: 'leverage', label: 'Leverage', icon: Gauge,
    blurb: 'Long & short positioning, market leverage and liquidation pressure — is leverage high or low, are traders leaning long or short, and where is the greater squeeze/liquidation risk right now.' },
  { id: 'macro', label: 'Macro & Policy', icon: Globe,
    blurb: 'Are global money conditions helping or hurting Bitcoin? Central-bank policy, a liquidity gauge, cross-market correlations and a regulation tracker.' },
  { id: 'news', label: 'News', icon: Newspaper,
    blurb: 'The news, explained: what happened, why it matters for Bitcoin, the likely direction and an impact score — with links to the original source.' },
  { id: 'risk', label: 'Risk', icon: ShieldAlert,
    blurb: 'How bumpy conditions are right now — kept separate from direction. Expected move, key support/resistance zones, event risk and data reliability. A positive outlook can still be high risk.' },
  { id: 'events', label: 'Events', icon: CalendarClock,
    blurb: 'A countdown calendar of the macro, derivatives and on-chain events that could move Bitcoin next — each with importance and expected volatility.' },
  { id: 'performance', label: 'Performance', icon: Trophy,
    blurb: 'The receipts. Every forecast is logged before the outcome is known and graded when it matures — accuracy, calibration and an honest scoreboard, plus the data-trust log. Nothing is hidden.' },
  { id: 'timemachine', label: 'Bitcoin Time Machine', icon: History,
    blurb: 'Replay any day in Bitcoin’s history: see exactly what the model would have predicted then, what actually happened next, and the price path around it — using only the information available at the time.' },
  { id: 'ask', label: 'Ask Albert', icon: MessageCircle,
    blurb: 'Chat with Albert, BTCIQ’s HuCentAI Quant Analyst, in plain English — "Why did the score fall?", "What could move Bitcoin next?" — grounded strictly in the live dashboard numbers. He never invents data.' },
  { id: 'alerts', label: 'Alerts', icon: Bell,
    blurb: 'A running feed of what just changed and what is coming: regime shifts, decision changes, data-trust drops and upcoming high-impact events.' },
  { id: 'network', label: 'Network & Sentiment', icon: Activity,
    blurb: 'Is the network healthy and how does the crowd feel? Live hashrate, mining difficulty, mempool congestion & fees, plus the Crypto Fear & Greed Index with Albert’s read on crowd extremes.' },
  { id: 'dataaudit', label: 'Data Audit', icon: Database,
    blurb: 'Where every number comes from and how much to trust it. A trust-scored composite Bitcoin price (median of Coinbase, Kraken, OKX, CoinGecko with outlier detection), broader cross-asset context, global news tone (GDELT) and US macro (FRED) — each tagged HIGH / MEDIUM / LOW confidence. No fabricated data.' },
  { id: 'settings', label: 'Settings', icon: Cpu,
    blurb: 'Admin passcode for manual forecast runs, the list of data sources and their status, and BTCIQ’s about & compliance information.' },
  { id: 'admin', label: 'Admin', icon: ShieldCheck,
    blurb: 'Integrations, data-source freshness, usage, costs and system health for the BTCIQ platform.' },
];

// Legacy section metadata for sub-panels that are now grouped under the new nav
// (their components still look up a blurb/label by id).
const LEGACY_SECTIONS = [
  { id: 'bitmark', label: 'BitMarkAI', icon: Sparkles,
    blurb: 'BitMarkAI is BTCIQ’s adaptive Bitcoin Price Prediction Engine — probability-based forecasts from one week to five years. Each horizon is weighted differently, updated weekly, on demand, or when a major event hits — and every change is explained. It never gives a single guaranteed price.' },
  { id: 'chart', label: 'Chart Intelligence', icon: CandlestickChart,
    blurb: 'An automatic read of the daily chart in plain language: support and resistance zones, trend, breakouts and momentum — plus how often similar setups played out historically.' },
  { id: 'cycle', label: 'Cycle', icon: Globe,
    blurb: 'Where Bitcoin sits in its ~4-year halving cycle and how money is rotating across the wider crypto market (BTC dominance). Context, not a price rule.' },
  { id: 'policy', label: 'Macro & Policy', icon: Landmark,
    blurb: 'Are global money conditions helping or hurting Bitcoin? Central-bank policy, a liquidity gauge, cross-market correlations and a regulation tracker that separates proposals from enacted law.' },
  { id: 'analysis', label: 'Indicators', icon: BarChart3,
    blurb: 'The evidence behind the score: each indicator category, the raw values the model reads, and which ones matter most right now.' },
  { id: 'scorecard', label: 'Prediction Ledger', icon: ClipboardList,
    blurb: 'Every forecast is permanently logged before the outcome is known, then graded when it matures — directional accuracy, Brier score, error and calibration by horizon. Nothing is deleted.' },
  { id: 'trust', label: 'Data Trust', icon: ShieldCheck,
    blurb: 'Where every number comes from: the source, how fresh it is, and how reliable. If a live feed goes stale the odds are automatically toned down.' },
];
const sec = (id) => SECTIONS.find(s => s.id === id)
  || LEGACY_SECTIONS.find(s => s.id === id)
  || { id, label: id, icon: Info, blurb: '' };

// Sections that are Bitcoin-specific and hidden from the nav when an altcoin is selected.
const BTC_ONLY_SECTIONS = ['smartmoney', 'whales', 'macro', 'events', 'timemachine', 'leverage', 'network', 'dataaudit', 'admin'];
// Sections removed from the app entirely (superseded by the global coin picker).
const REMOVED_SECTIONS = ['compare'];
// The currently-selected coin flows through this context so deep components
// (Albert insights, Ask Albert chat) fetch data for the right asset.
const SymbolContext = React.createContext('BTC');

/* --------------------------- Error Boundary ------------------------- */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('BTCIQ ErrorBoundary caught:', this.props.label || '', error, info);
  }
  componentDidUpdate(prevProps) {
    // Reset the boundary when the key context (e.g. active section) changes.
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }
  render() {
    if (this.state.hasError) {
      if (this.props.silent) return null;
      return (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.06] p-5 text-sm">
          <p className="font-semibold text-amber-300">This panel hit a snag{this.props.label ? ` (${this.props.label})` : ''}.</p>
          <p className="mt-1 text-slate-400">The rest of BTCIQ is still live. You can retry just this panel.</p>
          <button onClick={() => this.setState({ hasError: false })}
            className="mt-3 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800">Retry</button>
        </div>
      );
    }
    return this.props.children;
  }
}

/* --------------------------- Loading Skeleton ----------------------- */
function Shimmer({ className = '', style }) {
  return <div className={`animate-pulse rounded-md bg-slate-800/70 ${className}`} style={style} />;
}

function DashboardSkeleton({ ticker }) {
  const navRows = Array.from({ length: 12 });
  return (
    <div className="flex min-h-screen bg-slate-950">
      {/* Sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-800 bg-slate-900/40 px-4 py-5 md:flex">
        <img src="/btciq-logo.png" alt="BTCIQ" className="mb-1 h-9 w-auto object-contain" />
        <div className="mb-6 text-[10px] text-slate-600">Powered by BitCentAI</div>
        <div className="space-y-1.5">
          {navRows.map((_, i) => (
            <div key={i} className="flex items-center gap-3 rounded-lg px-3 py-2">
              <Shimmer className="h-4 w-4 rounded" />
              <Shimmer className="h-3.5" style={{ width: `${55 + ((i * 7) % 35)}%` }} />
            </div>
          ))}
        </div>
        <div className="mt-auto rounded-xl border border-slate-800 bg-slate-900/60 p-3">
          <Shimmer className="mb-2 h-3 w-20" />
          <Shimmer className="h-6 w-16" />
        </div>
      </aside>
      {/* Main */}
      <div className="flex-1">
        {/* Top bar with LIVE price (progressive hydration) */}
        <div className="flex items-center gap-3 border-b border-slate-800 px-4 py-3 md:px-8">
          <Shimmer className="h-8 w-24 rounded-lg" />
          {ticker && ticker.price ? (
            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1 text-[11px] font-bold text-emerald-400"><span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />LIVE</span>
              <span className="text-lg font-bold text-white">{fmtUsd(ticker.price)}</span>
              {ticker.price_aud && <span className="rounded-md bg-amber-500/10 px-1.5 py-0.5 text-xs font-semibold text-amber-300">≈ {fmtAud(ticker.price_aud)}</span>}
              {typeof ticker.change24h === 'number' && <span className={`text-sm font-semibold ${ticker.change24h >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{ticker.change24h}%</span>}
            </div>
          ) : (
            <Shimmer className="h-6 w-40" />
          )}
          <div className="ml-auto flex items-center gap-2">
            <Shimmer className="h-8 w-8 rounded-lg" />
            <Shimmer className="h-8 w-20 rounded-lg" />
          </div>
        </div>
        {/* Overview-shaped skeleton */}
        <main className="mx-auto max-w-6xl space-y-4 px-4 py-6 md:px-8">
          <div className="flex items-center gap-3">
            <Shimmer className="h-8 w-8 rounded-lg" />
            <Shimmer className="h-6 w-40" />
          </div>
          {/* Albert review card */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6">
            <div className="mb-3 flex items-center gap-2"><Shimmer className="h-9 w-9 rounded-full" /><Shimmer className="h-4 w-32" /></div>
            <Shimmer className="mb-2 h-3 w-full" /><Shimmer className="mb-2 h-3 w-[92%]" /><Shimmer className="h-3 w-[70%]" />
          </div>
          {/* KPI tiles row */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
                <Shimmer className="mb-2 h-3 w-16" />
                <Shimmer className="mb-1 h-7 w-14" />
                <Shimmer className="h-3 w-20" />
              </div>
            ))}
          </div>
          {/* Chart + side panel */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 lg:col-span-2">
              <Shimmer className="mb-4 h-4 w-48" />
              <Shimmer className="h-56 w-full rounded-lg" />
            </div>
            <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
              <Shimmer className="h-4 w-32" />
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3"><Shimmer className="h-8 w-8 rounded-lg" /><div className="flex-1"><Shimmer className="mb-1 h-3 w-full" /><Shimmer className="h-3 w-[60%]" /></div></div>
              ))}
            </div>
          </div>
          <p className="pt-2 text-center text-xs text-slate-600">Building your live Bitcoin intelligence… core price is already live above.</p>
        </main>
      </div>
    </div>
  );
}

/* --------------------------- small components ------------------------ */
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/95 px-3 py-2 shadow-xl">
      <p className="mb-1 text-xs font-bold text-slate-400">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="text-xs" style={{ color: p.color }}>
          {p.name}: {p.name && p.name.includes('Price') ? fmtUsd(p.value) : fmtPct(p.value)}
        </p>
      ))}
    </div>
  );
}

function QuantGauge({ score }) {
  const r = 54;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score || 0));
  const dash = (c * pct) / 100;
  const color = scoreColor(score);
  return (
    <div className="relative flex h-44 w-44 items-center justify-center">
      <svg className="h-44 w-44 -rotate-90" viewBox="0 0 120 120">
        <circle cx="60" cy="60" r={r} fill="none" stroke="#1e293b" strokeWidth="12" />
        <circle cx="60" cy="60" r={r} fill="none" stroke={color} strokeWidth="12"
          strokeLinecap="round" strokeDasharray={`${dash} ${c}`} />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-5xl font-black text-white">{score}</span>
        <span className="text-[11px] text-slate-500">/ 100</span>
      </div>
    </div>
  );
}

const InfoBlock = ({ children }) => (
  <div className="flex gap-3 rounded-lg border border-sky-500/20 bg-sky-500/[0.04] p-4 text-sm text-slate-400">
    <img src="/albert.png" alt="Albert" className="h-9 w-9 shrink-0 rounded-full object-cover ring-2 ring-sky-500/40" />
    <div>
      <div className="mb-0.5 flex items-center gap-2">
        <span className="font-semibold text-sky-200">Albert</span>
        <span className="text-[11px] font-normal text-slate-500">· in plain English</span>
      </div>
      <div>{children}</div>
    </div>
  </div>
);

// Reusable explainer tooltip. Shows on hover AND on tap/click (mobile-friendly). Bigger, readable popup.
function InfoTip({ text, below = true, className = '' }) {
  const [open, setOpen] = React.useState(false);
  return (
    <span
      className={`group/info relative inline-flex cursor-help align-middle text-slate-500 hover:text-sky-400 ${className}`}
      onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <Info className="h-3.5 w-3.5" />
      {open && (
        <span className={`absolute left-1/2 z-[70] w-72 max-w-[80vw] -translate-x-1/2 animate-in fade-in-0 zoom-in-95 duration-200 ease-out ${below ? 'top-full mt-2 origin-top slide-in-from-top-1' : 'bottom-full mb-2 origin-bottom slide-in-from-bottom-1'}`}>
          <span className={`absolute left-1/2 h-3 w-3 -translate-x-1/2 rotate-45 rounded-[2px] bg-slate-900 ${below ? '-top-1.5 border-l border-t border-slate-600' : '-bottom-1.5 border-b border-r border-slate-600'}`} />
          <span className="relative block rounded-xl border border-slate-600 bg-slate-900 px-4 py-3 text-[13px] font-normal normal-case leading-relaxed tracking-normal text-slate-100 shadow-2xl">
            {text}
          </span>
        </span>
      )}
    </span>
  );
}

// Whole-card explainer: the entire wrapped area is a hover/tap target that reveals a big popup.
function TapInfo({ text, className = '', below = true, children }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div
      className={`group/info relative cursor-help ${className}`}
      onClick={() => setOpen((o) => !o)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      {text && <span className="absolute right-2 top-2 z-10 text-slate-500 transition-colors group-hover/info:text-sky-400"><Info className="h-3.5 w-3.5" /></span>}
      {children}
      {text && open && (
        <div className={`absolute left-1/2 z-[70] w-72 max-w-[80vw] -translate-x-1/2 animate-in fade-in-0 zoom-in-95 duration-200 ease-out ${below ? 'top-full mt-2 origin-top slide-in-from-top-1' : 'bottom-full mb-2 origin-bottom slide-in-from-bottom-1'}`}>
          <div className={`absolute left-1/2 h-3 w-3 -translate-x-1/2 rotate-45 rounded-[2px] bg-slate-900 ${below ? '-top-1.5 border-l border-t border-slate-600' : '-bottom-1.5 border-b border-r border-slate-600'}`} />
          <div className="relative rounded-xl border border-slate-600 bg-slate-900 px-4 py-3 text-[13px] leading-relaxed text-slate-100 shadow-2xl">
            {text}
          </div>
        </div>
      )}
    </div>
  );
}



function AiReview({ text, voice = true, section, footer }) {
  const symbol = React.useContext(SymbolContext);
  const [speaking, setSpeaking] = React.useState(false);
  const [techOpen, setTechOpen] = React.useState(false);
  const [cache, setCache] = React.useState({ plain: null, technical: null });
  const [genAt, setGenAt] = React.useState({ plain: null, technical: null });
  const [now, setNow] = React.useState(Date.now());
  const [loading, setLoading] = React.useState(!!section);

  const load = React.useCallback((m, force) => {
    if (!section) return;
    setLoading(true);
    fetch(`/api/v1/albert/insight?section=${encodeURIComponent(section)}&mode=${m}&symbol=${encodeURIComponent(symbol)}${force ? '&refresh=1' : ''}`)
      .then((r) => r.json())
      .then((j) => { if (j && j.status === 'ready' && j.text) { setCache((c) => ({ ...c, [m]: j.text })); setGenAt((g) => ({ ...g, [m]: j.generated_at || new Date().toISOString() })); } })
      .catch(() => { /* keep fallback */ })
      .finally(() => setLoading(false));
  }, [section, symbol]);

  // Reset cached insight whenever the coin changes so we never show the wrong asset.
  React.useEffect(() => { setCache({ plain: null, technical: null }); setGenAt({ plain: null, technical: null }); }, [symbol]);
  React.useEffect(() => { if (section) load('plain'); }, [section, symbol, load]);
  // tick for "updated X ago" + auto-refresh on new compute data every 5 min (cached, cheap)
  React.useEffect(() => {
    if (!section) return;
    const tick = setInterval(() => setNow(Date.now()), 30000);
    const refresh = setInterval(() => load('plain'), 300000);
    return () => { clearInterval(tick); clearInterval(refresh); };
  }, [section, load]);

  const openTech = () => { setTechOpen(true); if (section && !cache.technical) load('technical'); };
  const regenerate = () => load('plain', true);

  const aiText = cache.plain;
  const shown = aiText || text;
  const agoLabel = (() => {
    const iso = genAt.plain;
    if (!iso) return null;
    const secs = Math.max(0, Math.floor((now - new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).getTime()) / 1000));
    if (secs < 60) return 'just now';
    const m = Math.floor(secs / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  })();

  const speak = () => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return;
    const synth = window.speechSynthesis;
    if (synth.speaking) { synth.cancel(); setSpeaking(false); return; }
    const u = new SpeechSynthesisUtterance(shown);
    const vs = synth.getVoices();
    const pick = vs.find((v) => /daniel|google uk english male|arthur|male/i.test(v.name) && /en/i.test(v.lang))
      || vs.find((v) => /google us english|english/i.test(v.name) && /en/i.test(v.lang))
      || vs.find((v) => /en/i.test(v.lang));
    if (pick) u.voice = pick;
    u.rate = 0.96; u.pitch = 1.05; u.volume = 1;
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    setSpeaking(true);
    synth.speak(u);
  };
  return (
    <Card className="border-0 bg-gradient-to-br from-sky-500/10 to-violet-500/[0.06] p-5 ring-1 ring-sky-500/25">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <img src="/albert.png" alt="Albert" className="h-8 w-8 rounded-full object-cover ring-2 ring-sky-500/40" />
        <h3 className="text-sm font-semibold text-sky-100">Albert’s Review</h3>
        {aiText ? (
          <span className="flex items-center gap-1 rounded-full bg-violet-500/20 px-2 py-0.5 text-[10px] font-semibold text-violet-200 ring-1 ring-violet-500/40"><Sparkles className="h-3 w-3" />AI insight</span>
        ) : loading ? (
          <span className="flex items-center gap-1.5 text-[10px] text-slate-400"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-violet-400" />Albert is thinking…</span>
        ) : null}
        {aiText && agoLabel && <span className="flex items-center gap-1 text-[10px] text-slate-500"><Clock className="h-2.5 w-2.5" />updated {agoLabel}</span>}

        <div className="ml-auto flex items-center gap-1.5">
          {section && (
            <button onClick={regenerate} disabled={loading} title="Ask Albert for a fresh take" className="rounded-full border border-slate-700 p-1.5 text-slate-300 transition-colors hover:border-sky-500/40 hover:text-sky-300 disabled:opacity-50">
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            </button>
          )}
          {voice && (
            <button onClick={speak} className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${speaking ? 'border-sky-400 bg-sky-500/20 text-sky-200' : 'border-slate-700 bg-slate-800/60 text-slate-300 hover:border-sky-500/40 hover:text-sky-300'}`}>
              {speaking ? <><VolumeX className="h-3.5 w-3.5" />Stop</> : <><Volume2 className="h-3.5 w-3.5" />Listen</>}
            </button>
          )}
        </div>
      </div>
      <p className={`whitespace-pre-line text-sm leading-relaxed text-slate-200 transition-opacity duration-300 ${loading && !aiText ? 'opacity-70' : 'opacity-100'}`}>{shown}</p>
      {section && (
        <button onClick={openTech} className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-violet-300 underline decoration-violet-500/40 underline-offset-2 transition-colors hover:text-violet-200">
          <Brain className="h-3.5 w-3.5" />Read Albert’s technical briefing
        </button>
      )}
      {footer && <div className="mt-3">{footer}</div>}

      {techOpen && (
        <div className="fixed inset-0 z-[130] flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm" onClick={() => setTechOpen(false)}>
          <div className="max-h-[86vh] w-full max-w-2xl overflow-auto rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-2xl animate-in fade-in-0 zoom-in-95 duration-200" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center gap-3">
              <img src="/albert.png" alt="Albert" className="h-9 w-9 rounded-full object-cover ring-2 ring-violet-500/40" />
              <div className="flex-1">
                <h3 className="flex items-center gap-1.5 text-base font-bold text-white"><Brain className="h-4 w-4 text-violet-300" />Technical Briefing</h3>
                <p className="text-[11px] text-slate-500">Albert’s deeper, indicator-level read · probability, not certainty</p>
              </div>
              <button onClick={() => { if (!cache.technical) return; load('technical', true); }} disabled={loading || !cache.technical} title="Regenerate" className="rounded-lg border border-slate-700 p-1.5 text-slate-400 transition-colors hover:border-violet-500/40 hover:text-violet-300 disabled:opacity-50">
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <button onClick={() => setTechOpen(false)} className="rounded-lg border border-slate-700 p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white"><X className="h-4 w-4" /></button>
            </div>
            {cache.technical ? (
              <p className="whitespace-pre-line text-sm leading-relaxed text-slate-200">{cache.technical}</p>
            ) : (
              <div className="flex items-center gap-2 py-6 text-sm text-slate-400">
                <span className="h-2 w-2 animate-pulse rounded-full bg-violet-400" />Albert is writing the technical briefing…
              </div>
            )}
            <p className="mt-4 border-t border-slate-800 pt-3 text-[11px] italic text-slate-500">Educational analysis of Bitcoin market data — not financial advice. Albert is an AI quant persona, not Albert Einstein.</p>
          </div>
        </div>
      )}
    </Card>
  );
}

const SectionHead = ({ icon: Icon, title, blurb, coin }) => {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="flex items-center gap-2">
      {coin ? <CoinIcon symbol={coin} size={28} className="ring-1 ring-slate-700" /> : <Icon className="h-6 w-6 text-sky-400" />}
      <h1 className="text-2xl font-bold tracking-tight text-white">{title}</h1>
      {blurb && (
        <div className="relative">
          <button
            type="button"
            aria-label="What is this section?"
            title="What is this section?"
            onClick={() => setOpen((o) => !o)}
            className={`flex h-7 w-7 items-center justify-center rounded-full border transition-colors ${open ? 'border-sky-400 bg-sky-500/20 text-sky-200' : 'border-sky-500/30 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20'}`}
          >
            <Info className="h-4 w-4" />
          </button>
          {open && (
            <>
              <div className="fixed inset-0 z-[70]" onClick={() => setOpen(false)} />
              <div className="absolute left-0 top-full z-[80] mt-2 w-[min(30rem,90vw)] origin-top-left animate-in fade-in-0 zoom-in-95 slide-in-from-top-1 duration-200 ease-out">
                {/* caret arrow anchored under the info button */}
                <div className="absolute -top-1.5 left-2.5 h-3 w-3 rotate-45 rounded-[2px] border-l border-t border-slate-700 bg-slate-900" />
                <div className="relative rounded-lg bg-slate-900 shadow-2xl ring-1 ring-slate-700">
                  <InfoBlock>{blurb}</InfoBlock>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

/* ---------------------------- AI reviews ----------------------------- */
const f24 = (d) => (d.forecasts || []).find((x) => x.horizon === '24H');
const fBy = (d, h) => (d.forecasts || []).find((x) => x.horizon === h);

function reviewOverview(d) {
  const f = f24(d);
  const lean = f ? (f.higher >= f.lower ? 'higher' : 'lower') : 'sideways';
  return `${d.coin_name || 'Bitcoin'}'s overall Quant Score is ${d.quant_score}/100 — ${d.quant_label} — and the market is in a "${d.regime.regime}" regime. ${d.regime.description} ${f ? `Over the next 24 hours the model leans ${lean} (${f.higher}% up vs ${f.lower}% down) with ${f.confidence.toLowerCase()} confidence.` : ''} Biggest support: ${d.factors.bullish[0]} Main risk: ${d.factors.risk[0]}`;
}
function reviewForecasts(d) {
  const a = fBy(d, '24H'), b = fBy(d, '7D'), c = fBy(d, '30D');
  if (!a || !b || !c) return 'Forecasts are still being generated.';
  const best = [a, b, c].sort((x, y) => y.confidence_pct - x.confidence_pct)[0];
  return `The near-term (24h) picture is ${a.higher >= a.lower ? 'mildly constructive' : 'cautious'} at ${a.higher}% higher, while the 30-day view leans ${c.higher >= c.lower ? 'up' : 'down'} (${Math.max(c.higher, c.lower)}% ${c.higher >= c.lower ? 'higher' : 'lower'}). The engine is most confident on the ${best.horizon} horizon (${best.confidence} · ~${best.accuracy}% historical hit-rate). Treat every number as odds, not a promise — the ${a.horizon} thesis is invalidated ${a.invalidation_dir} ${fmtUsd(a.invalidation)}.`;
}
function reviewAnalysis(d) {
  const active = d.quant_breakdown.filter((b) => b.active);
  const strong = [...active].sort((x, y) => y.score - x.score)[0];
  const weak = [...active].sort((x, y) => x.score - y.score)[0];
  const topFeat = d.importances[0];
  return `Right now ${strong.name} is the most supportive category (${strong.score}/100, ${strong.signal}) while ${weak.name} is the weakest (${weak.score}/100, ${weak.signal}). The model currently weights ${topFeat.label} most heavily (${topFeat.importance}% importance). Across time-series cross-validation the model averages ${d.cv_mean}% accuracy on ${d.n_samples} days of real data — a realistic edge over a 50% coin-flip, not a crystal ball.`;
}
function reviewPerformance(d) {
  const sb = d.scoreboard;
  const edge = (sb.winRate - 50).toFixed(1);
  const streak = sb.currentStreak >= 0 ? `${sb.currentStreak} correct in a row` : `${Math.abs(sb.currentStreak)} wrong in a row`;
  return `Across ${sb.total} graded out-of-sample predictions the engine is right ${sb.winRate}% of the time — ${edge >= 0 ? `+${edge}` : edge} points versus a coin-flip — with a best run of ${sb.bestWinStreak} straight wins and currently ${streak}. These are honest, non-deleted results. Forward-live tracking has ${d.live_record.tracked} signal(s) logged and grades automatically as each new daily candle closes${d.live_record.winRate != null ? ` (live hit-rate ${d.live_record.winRate}%)` : ''}.`;
}
function reviewChart(d) {
  const c = d.chart; if (!c) return 'Chart analysis is being generated.';
  const p = c.predictive;
  const keySig = c.signals.find((s) => s.bias !== 'Neutral') || c.signals[0];
  return `The daily chart shows a ${c.structure.toLowerCase()} structure. ${p.primary_setup} Historically, similar setups broke higher ${p.breakout_up}% of the time and lower ${p.breakdown}% within five days. ${keySig ? `Most notable signal right now: ${keySig.type} (${keySig.bias}).` : ''} The detection engine finds the levels; the probabilities come from base rates in ${d.n_samples} days of real data — not opinion.`;
}
function reviewCycle(d) {
  const c = d.cycle, dom = d.dominance;
  const cyc = c ? `Bitcoin is ~${c.cycle_progress_pct}% through its 4-year halving cycle (${c.days_since_halving} days since the ${c.last_halving_date} halving, block reward ${c.reward} BTC). The calendar-plus-price read places it in a "${c.phase}" phase, with the next halving an estimated ${c.est_days_to_next} days away.` : '';
  const dtxt = dom ? ` BTC dominance is ${dom.dominance}% (${dom.direction.toLowerCase()}), total crypto market cap ~$${dom.total_mcap_t}T — ${dom.interpretation}` : '';
  return `${cyc}${dtxt} Cycle timing is context, not a price rule — every cycle has played out under different liquidity and macro conditions.`;
}

/* --------------------------- sections -------------------------------- */
const riskColor = (lvl) => ({
  Low: 'text-emerald-400', Moderate: 'text-lime-400', Elevated: 'text-amber-400',
  High: 'text-orange-400', Extreme: 'text-red-400',
}[lvl] || 'text-slate-300');
const riskRing = (lvl) => ({
  Low: 'ring-emerald-500/30', Moderate: 'ring-lime-500/30', Elevated: 'ring-amber-500/30',
  High: 'ring-orange-500/30', Extreme: 'ring-red-500/30',
}[lvl] || 'ring-slate-800');
const alignColor = (a) => (a || '').includes('Bullish') ? 'text-emerald-400'
  : (a || '').includes('Bearish') ? 'text-red-400'
  : (a || '').includes('Conflict') ? 'text-amber-400' : 'text-slate-300';

function TechnicalBreakdownLink({ d, dec }) {
  const [open, setOpen] = React.useState(false);
  const fc = d.forecasts || [];
  return (
    <span className="mt-3 inline-block">
      <button onClick={() => setOpen(true)} className="inline-flex items-center gap-1.5 text-xs font-semibold text-sky-400 underline decoration-sky-500/40 underline-offset-2 transition-colors hover:text-sky-300">
        <Brain className="h-3.5 w-3.5" />Want the more technical summary? Open the breakdown
      </button>
      {open && (
        <div className="fixed inset-0 z-[130] flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm" onClick={() => setOpen(false)}>
          <div className="max-h-[86vh] w-full max-w-2xl overflow-auto rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center gap-3">
              <img src="/albert.png" alt="Albert" className="h-9 w-9 rounded-full object-cover ring-2 ring-sky-500/40" />
              <div className="flex-1">
                <h3 className="text-base font-bold text-white">Technical Breakdown</h3>
                <p className="text-[11px] text-slate-500">The numbers behind Albert’s bottom line · probability, not certainty</p>
              </div>
              <button onClick={() => setOpen(false)} className="rounded-lg border border-slate-700 p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white"><X className="h-4 w-4" /></button>
            </div>

            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              <div className="rounded-lg bg-slate-950/60 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Overall</p><p className="text-xl font-black" style={{ color: scoreColor(dec.overall_score) }}>{dec.overall_score}<span className="text-xs font-medium text-slate-500">/100</span></p><p className="text-[11px] text-slate-400">{dec.label}</p></div>
              <div className="rounded-lg bg-slate-950/60 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Regime</p><p className="text-sm font-bold leading-tight text-white">{dec.regime}</p></div>
              <div className="rounded-lg bg-slate-950/60 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Risk</p><p className={`text-xl font-black ${riskColor(dec.risk_level)}`}>{dec.risk_level}</p><p className="text-[11px] text-slate-500">index {dec.risk_score}/100</p></div>
              <div className="rounded-lg bg-slate-950/60 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Alignment</p><p className={`text-sm font-bold leading-tight ${alignColor(dec.alignment)}`}>{dec.alignment}</p></div>
            </div>

            <p className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wider text-slate-500">Signal composition</p>
            <div className="overflow-hidden rounded-lg border border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-950/60 text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="px-3 py-2 text-left font-medium">Signal group</th><th className="px-3 py-2 text-right font-medium">Score /100</th><th className="px-3 py-2 text-right font-medium">Weight</th></tr></thead>
                <tbody>
                  {(dec.components || []).map((c) => (
                    <tr key={c.name} className="border-t border-slate-800/70">
                      <td className="px-3 py-2 text-slate-300">{c.name}</td>
                      <td className="px-3 py-2 text-right font-mono font-bold" style={{ color: scoreColor(c.score) }}>{c.score}</td>
                      <td className="px-3 py-2 text-right text-slate-400">{c.weight}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {fc.length > 0 && (<>
              <p className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wider text-slate-500">Directional odds & invalidation</p>
              <div className="overflow-hidden rounded-lg border border-slate-800">
                <table className="w-full text-sm">
                  <thead className="bg-slate-950/60 text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="px-3 py-2 text-left font-medium">Horizon</th><th className="px-3 py-2 text-right font-medium">Higher</th><th className="px-3 py-2 text-right font-medium">Confidence</th><th className="px-3 py-2 text-right font-medium">Backtest</th><th className="px-3 py-2 text-right font-medium">Invalidated</th></tr></thead>
                  <tbody>
                    {fc.map((f) => (
                      <tr key={f.horizon} className="border-t border-slate-800/70">
                        <td className="px-3 py-2 font-semibold text-slate-200">{f.horizon}</td>
                        <td className="px-3 py-2 text-right font-mono" style={{ color: scoreColor(f.higher) }}>{f.higher}%</td>
                        <td className="px-3 py-2 text-right text-slate-300">{f.confidence} ({f.confidence_pct}%)</td>
                        <td className="px-3 py-2 text-right text-slate-400">{f.accuracy}%</td>
                        <td className="px-3 py-2 text-right font-mono text-amber-400">{f.invalidation_dir} {fmtUsd(f.invalidation)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>)}

            <p className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wider text-slate-500">Model & data</p>
            <div className="flex flex-wrap gap-2 text-[11px]">
              {d.cv_mean != null && <span className="rounded-full bg-slate-800/70 px-2.5 py-1 text-slate-300">Cross-val accuracy {d.cv_mean}% · {d.n_samples} days</span>}
              {d.scoreboard && <span className="rounded-full bg-slate-800/70 px-2.5 py-1 text-slate-300">Live win rate {d.scoreboard.winRate}% ({d.scoreboard.total} graded)</span>}
              {dec.data_trust && <span className="rounded-full bg-slate-800/70 px-2.5 py-1 text-slate-300">Data trust {dec.data_trust.score}/100{dec.odds_faded ? ' · odds faded' : ''}</span>}
              <span className="rounded-full bg-slate-800/70 px-2.5 py-1 text-slate-300">Quant Score {d.quant_score}/100</span>
            </div>
            <p className="mt-5 text-[11px] leading-relaxed text-slate-500">Every figure is derived from real market data and historical base rates. These are probabilities and research signals — not financial advice or a guarantee of future outcomes.</p>
          </div>
        </div>
      )}
    </span>
  );
}

function DecisionEngineCard({ d }) {
  const dec = d.decision;
  if (!dec) return null;
  const coinName = d.coin_name || 'Bitcoin';
  const sym = d.symbol || 'BTC';
  return (
    <Card className="border-0 bg-gradient-to-br from-amber-500/[0.07] via-violet-500/[0.08] to-slate-900 p-6 ring-1 ring-violet-500/30 shadow-xl shadow-violet-950/30">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Brain className="h-5 w-5 text-amber-400" />
        <h3 className="text-lg font-bold text-white">{coinName} Market State</h3>
        <span className="text-[11px] text-slate-500">Unified Decision Engine · reconciles every signal</span>
        {dec.data_trust && <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${dec.data_trust.faded ? 'border-orange-500/30 text-orange-300' : 'border-emerald-500/25 text-emerald-300'}`}>Data trust {dec.data_trust.score}{dec.odds_faded ? ' · odds faded' : ''}</span>}
        <Badge variant="outline" className={`ml-auto border-slate-700 ${alignColor(dec.alignment)}`}>{dec.alignment}</Badge>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <TapInfo below text="The single 0–100 conviction score blending every signal group. Above 55 leans bullish, below 45 bearish, near 50 is undecided." className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="pr-4 text-[11px] uppercase tracking-wider text-slate-400">Overall Score</p>
          <p className="mt-1 text-4xl font-black" style={{ color: scoreColor(dec.overall_score) }}>{dec.overall_score}</p>
          <p className="text-sm font-semibold" style={{ color: scoreColor(dec.overall_score) }}>{dec.label}</p>
        </TapInfo>
        <TapInfo below text={`The market character the engine has classified ${sym} into right now (e.g. trend, range, or volatile) — it sets the playbook for reading every other signal.`} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="pr-4 text-[11px] uppercase tracking-wider text-slate-400">Market Regime</p>
          <p className="mt-1 text-lg font-bold leading-tight text-white">{dec.regime}</p>
        </TapInfo>
        <TapInfo below text="How turbulent conditions are now (0–100 risk index). It's about the size of the swings, not their direction — you can lean up and still be high-risk." className={`rounded-xl border border-slate-800 bg-slate-950/50 p-4 ring-1 ${riskRing(dec.risk_level)}`}>
          <p className="flex items-center gap-1 pr-4 text-[11px] uppercase tracking-wider text-slate-400"><ShieldAlert className="h-3 w-3" />Risk Level</p>
          <p className={`mt-1 text-2xl font-black ${riskColor(dec.risk_level)}`}>{dec.risk_level}</p>
          <p className="text-[11px] text-slate-500">risk index {dec.risk_score}/100</p>
        </TapInfo>
        <TapInfo below text="Whether the signal groups agree. 'Mixed' means they disagree so conviction is lower; strong alignment means they point the same way." className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="flex items-center gap-1 pr-4 text-[11px] uppercase tracking-wider text-slate-400"><Scale className="h-3 w-3" />Signal Alignment</p>
          <p className={`mt-1 text-sm font-bold leading-tight ${alignColor(dec.alignment)}`}>{dec.alignment}</p>
        </TapInfo>
      </div>

      {/* component contributions */}
      <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-4">
        {dec.components.map((c) => (
          <div key={c.name} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-1 text-slate-400">{c.name}<InfoTip text={`${c.name} scores 0–100 and carries ${c.weight}% of the overall decision. Higher = more supportive of upside.`} /></span>
              <span className="font-mono font-bold" style={{ color: scoreColor(c.score) }}>{c.score}</span>
            </div>
            <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
              <div className="h-full rounded-full" style={{ width: `${c.score}%`, backgroundColor: scoreColor(c.score) }} />
            </div>
            <p className="mt-1 text-[10px] text-slate-500">weight {c.weight}%</p>
          </div>
        ))}
      </div>

      {/* multi-horizon outlook 24H → 1Y */}
      <div className="mt-5">
        <p className="mb-2 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Directional Outlook · 24 hours to 1 year<InfoTip text={`The model's estimated odds that ${sym} is higher or lower over each horizon. 'news-adj.' means recent headlines nudged the number. Odds, not promises.`} /></p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {dec.outlook.map((o) => {
            const up = o.lean === 'UP';
            return (
              <div key={o.horizon} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-center">
                <p className="text-[11px] font-medium text-slate-400">{o.label}</p>
                <p className={`mt-1 flex items-center justify-center gap-1 text-lg font-black ${up ? 'text-emerald-400' : 'text-red-400'}`}>
                  {up ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}{Math.max(o.higher, o.lower)}%
                </p>
                <p className={`text-[10px] ${up ? 'text-emerald-400/80' : 'text-red-400/80'}`}>{up ? 'higher' : 'lower'}</p>
                {o.news_adjusted && <p className="mt-0.5 text-[9px] text-violet-400/80">news-adj.</p>}
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}

function timeAgo(iso) {
  if (!iso) return '—';
  const t = Date.now() - new Date(iso).getTime();
  if (isNaN(t)) return '—';
  const m = Math.floor(t / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m} minute${m === 1 ? '' : 's'} ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hour${h === 1 ? '' : 's'} ago`;
  return `${Math.floor(h / 24)}d ago`;
}
const RISK_TXT = {
  Low: 'text-emerald-400', Normal: 'text-lime-400', Moderate: 'text-lime-400',
  Elevated: 'text-amber-400', High: 'text-orange-400', Extreme: 'text-red-400',
};

function MiniSpark({ points, height = 20, width = 72 }) {
  const vals = (points || []).map((p) => (p && typeof p.dominance === 'number' ? p.dominance : null)).filter((v) => v != null);
  if (vals.length < 2) {
    return <p className="mt-1 text-[9px] italic text-slate-600">building history…</p>;
  }
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const rng = (max - min) || 1;
  const step = width / (vals.length - 1);
  const path = vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(height - ((v - min) / rng) * (height - 3) - 1.5).toFixed(1)}`).join(' ');
  const up = vals[vals.length - 1] >= vals[0];
  const stroke = up ? '#34d399' : '#f87171';
  return (
    <svg width={width} height={height} className="mt-1.5 block" aria-hidden>
      <path d={path} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function StateItem({ label, value, sub, color, big, hint, spark }) {
  return (
    <TapInfo text={hint} className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
      <p className="flex items-center gap-1 pr-4 text-[10px] font-medium uppercase tracking-wider text-slate-500">
        {label}
      </p>
      <p className={`mt-1 font-black ${big ? 'text-2xl' : 'text-lg'}`} style={color ? { color } : undefined}>{value}</p>
      {sub && <p className="text-[11px] text-slate-500">{sub}</p>}
      {spark}
    </TapInfo>
  );
}

function MarketStateHero({ d, ticker }) {
  const ch = ticker?.change24h ?? d.day_change_pct;
  const f24o = f24(d);
  const f7o = fBy(d, '7D');
  const risk = d.risk || {};
  const riskLevel = risk.level || (d.decision && d.decision.risk_level) || '—';
  const dec = d.decision || {};
  const modelConf = f7o?.confidence || f24o?.confidence || '—';
  const dh = d.data_health || {};
  const sym = d.symbol || 'BTC';
  const coinName = d.coin_name || 'Bitcoin';
  return (
    <Card className="relative overflow-hidden border-0 bg-gradient-to-br from-slate-900 to-slate-900/60 p-6 ring-1 ring-slate-800">
      <div aria-hidden className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-amber-500/5 blur-3xl" />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <span className="flex items-center gap-1.5 text-xs font-bold text-emerald-400">
          <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" /><span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" /></span>
          {coinName.toUpperCase()} MARKET STATE
        </span>
        <span className="ml-auto text-[11px] text-slate-500">Updated {timeAgo(d.created_at)} · source {d.data_source}</span>
      </div>

      <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
        <div className="flex items-center gap-3">
          <CoinIcon symbol={sym} size={44} className="shadow-lg" />
          <div>
            <p className="text-[10px] uppercase tracking-wider text-slate-500">{sym} Live Price</p>
            <p className="text-4xl font-black text-white">{fmtUsd(ticker?.price ?? d.last_close)}</p>
            <p className={`text-sm font-semibold ${ch >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {ch >= 0 ? '▲' : '▼'} {ch}% (24h){ticker?.price_aud ? ` · ≈ ${fmtAud(ticker.price_aud)}` : ''}
            </p>
          </div>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wider text-slate-500">Market Regime</p>
          <p className="text-2xl font-bold text-sky-300">{d.regime.regime}</p>
          <p className="max-w-md text-xs text-slate-500">{d.regime.description}</p>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
        <StateItem label="Quant Score" value={`${d.quant_score}`} sub={d.quant_label} color={scoreColor(d.quant_score)} big
          hint={`A 0–100 health score for ${coinName} right now. Above 55 leans positive, below 45 leans negative, near 50 is undecided.`} />
        <StateItem label="24-Hour Outlook" value={f24o ? `${Math.max(f24o.higher, f24o.lower)}%` : '—'} sub={f24o ? (f24o.higher >= f24o.lower ? 'prob. higher' : 'prob. lower') : ''} color={f24o && f24o.higher >= f24o.lower ? '#34d399' : '#f87171'}
          hint={`The model's estimated chance that ${coinName} closes higher (or lower) one day from now. It's odds, not a promise.`} />
        <StateItem label="7-Day Outlook" value={f7o ? `${Math.max(f7o.higher, f7o.lower)}%` : '—'} sub={f7o ? (f7o.higher >= f7o.lower ? 'prob. higher' : 'prob. lower') : ''} color={f7o && f7o.higher >= f7o.lower ? '#34d399' : '#f87171'}
          hint="Same idea as the 24-hour view, but looking one week ahead." />
        <StateItem label="Risk Level" value={riskLevel} sub="how bumpy, not direction" color={undefined}
          hint="How wild price swings could be right now — separate from whether the outlook is up or down. You can be 'leaning up' AND 'high risk' at the same time." />
        <StateItem label="Model Confidence" value={modelConf} sub="how sure the model is" hint="How strong the model's own conviction is, based on how well it has done in similar past setups." />
        <StateItem label="Market Share" value={d.dominance ? `${d.dominance.dominance}%` : '—'}
          sub={d.dominance ? `of $${d.dominance.total_mcap_t}T${d.dominance.direction && d.dominance.direction !== 'Neutral' ? ` · ${d.dominance.direction}` : ''}` : ''}
          spark={d.dominance ? <MiniSpark points={d.dominance.history} /> : null}
          hint={`${coinName}'s share of the total crypto market cap (its "dominance"), with a mini trend of the last few days once history builds up. Rising share means capital is rotating toward it; falling share means the rest of the market is outpacing it.`} />
        <StateItem label="Data Confidence" value={dh.level || '—'} sub={dh.score != null ? `${dh.score}/100 feeds` : ''} hint="How fresh and reliable the underlying data feeds are. If feeds go stale, the odds are automatically toned down." />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        <span className={`rounded-full px-2 py-0.5 font-semibold ${RISK_TXT[riskLevel] || 'text-slate-300'} bg-slate-800/60`}>Risk: {riskLevel}</span>
        {dec.label && <span className="rounded-full bg-slate-800/60 px-2 py-0.5 font-semibold text-slate-300">Decision: {dec.label} ({dec.overall_score}/100)</span>}
        <span className="rounded-full bg-slate-800/60 px-2 py-0.5">Alignment: {dec.alignment || '—'}</span>
        <span className="ml-auto italic">Probability, not certainty — not financial advice.</span>
      </div>
    </Card>
  );
}

function AlbertIntroCard() {
  return (
    <Card className="flex items-start gap-4 border-0 bg-gradient-to-br from-sky-500/5 to-violet-500/5 p-5 ring-1 ring-sky-500/20">
      <img src="/albert.png" alt="Albert" className="h-16 w-16 shrink-0 rounded-full object-cover ring-2 ring-sky-500/40" />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-base font-bold text-white">Albert</h3>
          <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] font-semibold text-sky-300">BTCIQ’s HuCentAI Quant Analyst</span>
        </div>
        <p className="mt-1 text-sm text-slate-300">Albert interprets BitMarkAI’s numbers, explains the probabilities in plain language, and helps you understand what may move the market next. “Let us examine the evidence — probability is not certainty.”</p>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-500">Albert is an original fictional BTCIQ HuCentAI Quant character inspired by the spirit of scientific curiosity. He is not Albert Einstein and does not represent Einstein’s real opinions.</p>
      </div>
    </Card>
  );
}

const TV_STUDIES = [
  { id: 'RSI@tv-basicstudies', label: 'RSI' },
  { id: 'MACD@tv-basicstudies', label: 'MACD' },
  { id: 'BB@tv-basicstudies', label: 'Bollinger Bands' },
  { id: 'MASimple@tv-basicstudies', label: 'SMA' },
  { id: 'MAExp@tv-basicstudies', label: 'EMA' },
  { id: 'Stochastic@tv-basicstudies', label: 'Stochastic' },
  { id: 'Volume@tv-basicstudies', label: 'Volume' },
];
const TV_INTERVALS = [['15', '15m'], ['60', '1h'], ['240', '4h'], ['D', '1D'], ['W', '1W']];
const TV_STYLES = [['1', 'Candles'], ['3', 'Line'], ['4', 'Area'], ['8', 'Heikin Ashi']];
const TV_SYMBOLS = ['COINBASE:BTCUSD', 'BINANCE:BTCUSDT', 'BITSTAMP:BTCUSD', 'KRAKEN:XBTUSD'];
const DEFAULT_PRESET = { symbol: 'COINBASE:BTCUSD', interval: 'D', style: '1', studies: ['RSI@tv-basicstudies'] };

function loadPreset() {
  if (typeof window === 'undefined') return DEFAULT_PRESET;
  try {
    const p = JSON.parse(window.localStorage.getItem('btciq_chart_preset'));
    if (p && p.symbol) return { ...DEFAULT_PRESET, ...p };
  } catch (e) { /* noop */ }
  return DEFAULT_PRESET;
}

function TradingViewChart({ height = 460 }) {
  const symbol = React.useContext(SymbolContext);
  const [fs, setFs] = React.useState(false);
  const [cfg, setCfg] = React.useState(false);
  const [preset, setPreset] = React.useState(DEFAULT_PRESET);
  const [draft, setDraft] = React.useState(DEFAULT_PRESET);
  const [saved, setSaved] = React.useState(false);
  const ref = React.useRef(null);

  React.useEffect(() => { const p = loadPreset(); setPreset(p); setDraft(p); }, []);

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // For altcoins, always follow the selected coin; BTC uses the saved preset symbol.
    const effSymbol = symbol === 'BTC' ? preset.symbol : `COINBASE:${symbol}USD`;
    el.innerHTML = '';
    const widget = document.createElement('div');
    widget.className = 'tradingview-widget-container__widget';
    widget.style.height = '100%';
    widget.style.width = '100%';
    el.appendChild(widget);
    const s = document.createElement('script');
    s.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    s.type = 'text/javascript';
    s.async = true;
    s.innerHTML = JSON.stringify({
      autosize: true, symbol: effSymbol, interval: preset.interval, timezone: 'Etc/UTC',
      theme: 'dark', style: preset.style, locale: 'en', allow_symbol_change: true,
      hide_side_toolbar: false, withdateranges: true, details: false, hotlist: false,
      calendar: false, studies: preset.studies || [], support_host: 'https://www.tradingview.com',
    });
    el.appendChild(s);
  }, [preset, symbol]);

  React.useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setFs(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const toggleStudy = (id) => setDraft((d) => ({
    ...d, studies: d.studies.includes(id) ? d.studies.filter((x) => x !== id) : [...d.studies, id],
  }));
  const savePreset = () => {
    setPreset(draft);
    if (typeof window !== 'undefined') window.localStorage.setItem('btciq_chart_preset', JSON.stringify(draft));
    setSaved(true); setTimeout(() => setSaved(false), 1800); setCfg(false);
  };
  const resetPreset = () => {
    setDraft(DEFAULT_PRESET); setPreset(DEFAULT_PRESET);
    if (typeof window !== 'undefined') window.localStorage.removeItem('btciq_chart_preset');
  };

  return (
    <Card className={`flex flex-col overflow-hidden border-0 bg-slate-900 p-0 ring-1 ring-slate-800 ${fs ? 'fixed inset-0 z-[100] rounded-none' : ''}`}>
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2">
        <div className="flex items-center gap-2">
          <CandlestickChart className="h-4 w-4 text-amber-400" />
          <span className="text-sm font-semibold text-white">{symbol === 'BTC' ? (preset.symbol.split(':')[1] || 'BTC/USD') : `${symbol}USD`} · Live Chart</span>
          <span className="hidden text-[10px] text-slate-500 sm:inline">TradingView · your saved preset</span>
        </div>
        <div className="flex items-center gap-1.5">
          {saved && <span className="text-[11px] font-semibold text-emerald-400">Preset saved ✓</span>}
          <button onClick={() => { setDraft(preset); setCfg(!cfg); }} className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium ${cfg ? 'border-sky-400 bg-sky-500/15 text-sky-200' : 'border-slate-700 text-slate-300 hover:bg-slate-800'}`}><SlidersHorizontal className="h-3.5 w-3.5" />Preset</button>
          <button onClick={() => setFs(!fs)} className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white">
            {fs ? <><Minimize2 className="h-3.5 w-3.5" />Exit</> : <><Maximize2 className="h-3.5 w-3.5" />Full screen</>}
          </button>
        </div>
      </div>

      {cfg && (
        <div className="border-b border-slate-800 bg-slate-950/60 p-4 text-sm">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-400">Symbol</p>
              <select value={draft.symbol} onChange={(e) => setDraft({ ...draft, symbol: e.target.value })} className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500/50 focus:outline-none">
                {TV_SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-400">Timeframe</p>
              <div className="flex flex-wrap gap-1">
                {TV_INTERVALS.map(([v, l]) => <button key={v} onClick={() => setDraft({ ...draft, interval: v })} className={`rounded px-2 py-1 text-xs ${draft.interval === v ? 'bg-sky-500/20 text-sky-200 ring-1 ring-sky-500/40' : 'bg-slate-800 text-slate-400'}`}>{l}</button>)}
              </div>
            </div>
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-400">Style</p>
              <div className="flex flex-wrap gap-1">
                {TV_STYLES.map(([v, l]) => <button key={v} onClick={() => setDraft({ ...draft, style: v })} className={`rounded px-2 py-1 text-xs ${draft.style === v ? 'bg-sky-500/20 text-sky-200 ring-1 ring-sky-500/40' : 'bg-slate-800 text-slate-400'}`}>{l}</button>)}
              </div>
            </div>
          </div>
          <div className="mt-3">
            <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-400">Indicators</p>
            <div className="flex flex-wrap gap-1.5">
              {TV_STUDIES.map((st) => (
                <button key={st.id} onClick={() => toggleStudy(st.id)} className={`rounded-full border px-2.5 py-1 text-xs ${draft.studies.includes(st.id) ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-200' : 'border-slate-700 bg-slate-800/60 text-slate-400'}`}>{draft.studies.includes(st.id) ? '✓ ' : ''}{st.label}</button>
              ))}
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <Button size="sm" onClick={savePreset} className="bg-sky-500 hover:bg-sky-400">Save preset</Button>
            <Button size="sm" variant="outline" onClick={resetPreset} className="border-slate-700 text-slate-300 hover:bg-slate-800">Reset</Button>
            <span className="text-[11px] text-slate-500">Saved to this browser · reloads automatically each visit. (Freehand drawings aren’t saved by the free widget.)</span>
          </div>
        </div>
      )}

      <div className="w-full" style={{ height: fs ? 'calc(100vh - 42px)' : height }}>
        <div ref={ref} className="tradingview-widget-container" style={{ height: '100%', width: '100%' }} />
      </div>
    </Card>
  );
}

function OverviewChart({ d }) {
  const [mode, setMode] = React.useState('tv');
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1 self-start rounded-lg border border-slate-800 bg-slate-900 p-0.5 text-xs">
        <button onClick={() => setMode('tv')} className={`rounded-md px-3 py-1 font-medium ${mode === 'tv' ? 'bg-sky-500/20 text-sky-200' : 'text-slate-400 hover:text-slate-200'}`}>TradingView</button>
        <button onClick={() => setMode('draw')} className={`rounded-md px-3 py-1 font-medium ${mode === 'draw' ? 'bg-sky-500/20 text-sky-200' : 'text-slate-400 hover:text-slate-200'}`}>Draw Board</button>
      </div>
      {mode === 'tv' ? <TradingViewChart /> : <DrawableChart ohlc={d.chart?.ohlc} />}
    </div>
  );
}

function OverviewSection({ d, ticker }) {
  return (
    <div className="space-y-5">
      <SectionHead icon={LayoutDashboard} title="Overview" blurb={SECTIONS[0].blurb} />
      <AiReview text={reviewOverview(d)} voice section="overview" footer={<TechnicalBreakdownLink d={d} dec={d.decision || {}} />} />
      {(d.symbol || 'BTC') === 'BTC' && <MorningBriefCard />}
      <MarketStateHero d={d} ticker={ticker} />
      <OverviewChart d={d} />
      <DecisionEngineCard d={d} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <div className="mb-3 flex items-center gap-2"><TrendingUp className="h-5 w-5 text-emerald-400" /><h3 className="font-semibold text-slate-100">Top Bullish Factors</h3></div>
          <ul className="space-y-2">
            {d.factors.bullish.map((t, i) => (
              <li key={i} className="flex gap-2 text-sm text-slate-300"><Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />{t}</li>
            ))}
          </ul>
        </Card>
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <div className="mb-3 flex items-center gap-2"><TrendingDown className="h-5 w-5 text-red-400" /><h3 className="font-semibold text-slate-100">Top Risk Factors</h3></div>
          <ul className="space-y-2">
            {d.factors.risk.map((t, i) => (
              <li key={i} className="flex gap-2 text-sm text-slate-300"><X className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />{t}</li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

function NewsLinkBar({ nl }) {
  const up = nl.delta > 0;
  const flat = nl.delta === 0;
  return (
    <div className="mt-3 rounded-lg border border-violet-500/25 bg-violet-500/5 p-3">
      <div className="flex items-center gap-2">
        <Newspaper className="h-3.5 w-3.5 text-violet-400" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-violet-300">News Forecast Link</span>
        <span className={`ml-auto text-xs font-bold ${up ? 'text-emerald-400' : flat ? 'text-slate-400' : 'text-red-400'}`}>{up ? '+' : ''}{nl.delta} pts</span>
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs">
        <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-slate-400">base {nl.higher_base}%</span>
        <span className="text-slate-500">→</span>
        <span className={`rounded px-2 py-0.5 font-mono font-bold ${up ? 'bg-emerald-500/10 text-emerald-400' : flat ? 'bg-slate-800 text-slate-300' : 'bg-red-500/10 text-red-400'}`}>adjusted {nl.higher_adj}%</span>
        <span className={`ml-auto rounded border px-1.5 py-0.5 text-[10px] font-semibold ${DIR_COLOR[(nl.bias || 'neutral').toLowerCase()]}`}>{nl.bias} news</span>
      </div>
      {nl.top_driver && <p className="mt-2 text-[11px] text-slate-500">Top driver: <span className="text-slate-400">{nl.top_driver}</span></p>}
    </div>
  );
}

function ForecastCard({ f }) {
  const sym = React.useContext(SymbolContext);
  const nl = f.news_link;
  const eff = nl ? nl.higher_adj : f.higher;
  const effLow = nl ? nl.lower_adj : f.lower;
  const bullish = eff >= 50;
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="mb-2 flex items-center gap-1.5">
        <img src="/albert.png" alt="Albert" className="h-5 w-5 rounded-full object-cover ring-1 ring-sky-500/50" />
        <span className="text-[10px] font-bold uppercase tracking-wider text-sky-300">Albert’s Call</span>
      </div>
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-1 text-lg font-bold text-white">{f.horizon} Forecast<InfoTip text={`The model's probability that ${sym} is higher vs lower at the end of this window, plus bull/base/bear price scenarios. Odds, not a promise.`} /></h3>
        <Badge variant="outline" className={`border-slate-700 ${bullish ? 'text-emerald-400' : 'text-red-400'}`}>{bullish ? 'Leans Up' : 'Leans Down'}</Badge>
      </div>
      <div className="mt-3">
        <div className="flex justify-between text-sm font-semibold"><span className="text-emerald-400">Higher {eff}%</span><span className="text-red-400">{effLow}% Lower</span></div>
        <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-red-500/40">
          <div className="h-full rounded-full bg-emerald-400" style={{ width: `${eff}%` }} />
        </div>
        {nl && <p className="mt-1 text-[10px] text-slate-500">base model {f.higher}% · adjusted by live news</p>}
      </div>
      {nl && <NewsLinkBar nl={nl} />}
      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-emerald-500/10 p-2"><p className="text-[10px] text-slate-400">Bull</p><p className="text-sm font-bold text-emerald-400">{fmtUsd(f.bull)}</p></div>
        <div className="rounded-lg bg-slate-800/60 p-2"><p className="text-[10px] text-slate-400">Base</p><p className="text-sm font-bold text-slate-200">{fmtUsd(f.base)}</p></div>
        <div className="rounded-lg bg-red-500/10 p-2"><p className="text-[10px] text-slate-400">Bear</p><p className="text-sm font-bold text-red-400">{fmtUsd(f.bear)}</p></div>
      </div>
      <div className="mt-4 space-y-1.5 text-xs">
        <div className="flex justify-between"><span className="flex items-center gap-1 text-slate-400">Expected range<InfoTip text="The likely high–low price band for this window based on recent volatility. Price can still move outside it." /></span><span className="font-mono text-slate-200">{fmtUsd(f.expected_low)} – {fmtUsd(f.expected_high)}</span></div>
        <div className="flex justify-between"><span className="flex items-center gap-1 text-slate-400">Confidence<InfoTip text="How strong the model's conviction is on this call, shown as a label and a 0–100%. Higher means the signal setup has been clearer historically." /></span><span className="font-semibold text-sky-400">{f.confidence} ({f.confidence_pct}%)</span></div>
        <div className="flex justify-between"><span className="flex items-center gap-1 text-slate-400">Backtest accuracy<InfoTip text="How often this type of call was correct in historical testing. A track-record hint, not a guarantee of the current call." /></span><span className="text-slate-200">{f.accuracy}%</span></div>
        <div className="flex justify-between"><span className="flex items-center gap-1 text-slate-400">Invalidated {f.invalidation_dir}<InfoTip text="The price level where this thesis is considered wrong. A move past it means the setup has broken and the forecast should be discarded." /></span><span className="font-mono text-amber-400">{fmtUsd(f.invalidation)}</span></div>
        <div className="flex justify-between"><span className="text-slate-400">Expires</span><span className="font-mono text-slate-400">{f.expiry}</span></div>
      </div>
      {f.contributions && f.contributions.length > 0 && (
        <div className="mt-4 border-t border-slate-800 pt-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Factor contributions (SHAP)</p>
          <div className="space-y-1">
            {f.contributions.slice(0, 4).map((ctr) => (
              <div key={ctr.feature} className="flex items-center gap-2 text-xs">
                <span className="w-28 shrink-0 truncate text-slate-400">{ctr.label}</span>
                <div className="flex h-3 flex-1 items-center">
                  <div className="flex w-1/2 justify-end">{ctr.contribution < 0 && <div className="h-2 rounded-l bg-red-400" style={{ width: `${Math.min(100, Math.abs(ctr.contribution) * 12)}%` }} />}</div>
                  <div className="flex w-1/2">{ctr.contribution >= 0 && <div className="h-2 rounded-r bg-emerald-400" style={{ width: `${Math.min(100, ctr.contribution * 12)}%` }} />}</div>
                </div>
                <span className={`w-12 shrink-0 text-right font-mono ${ctr.contribution >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{ctr.contribution >= 0 ? '+' : ''}{ctr.contribution}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

function ForecastsSection({ d }) {
  return (
    <div className="space-y-5">
      <SectionHead icon={Target} title="Forecasts" blurb={SECTIONS[1].blurb} coin={d.symbol || 'BTC'} />
      <AiReview text={reviewForecasts(d)} section="forecasts" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {(d.forecasts || []).map((f) => <ForecastCard key={f.horizon} f={f} />)}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <div className="mb-3 flex items-center gap-2">
            <img src="/albert.png" alt="Albert" className="h-8 w-8 shrink-0 rounded-full object-cover ring-2 ring-emerald-500/40" />
            <div>
              <h3 className="flex items-center gap-1.5 font-semibold text-slate-100"><TrendingUp className="h-4 w-4 text-emerald-400" />Albert’s Call · Why it could go up</h3>
              <p className="text-[11px] text-slate-500">Albert’s read of the bullish evidence</p>
            </div>
          </div>
          <ul className="space-y-2">{d.factors.bullish.map((t, i) => <li key={i} className="flex gap-2 text-sm text-slate-300"><Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />{t}</li>)}</ul>
        </Card>
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <div className="mb-3 flex items-center gap-2">
            <img src="/albert.png" alt="Albert" className="h-8 w-8 shrink-0 rounded-full object-cover ring-2 ring-red-500/40" />
            <div>
              <h3 className="flex items-center gap-1.5 font-semibold text-slate-100"><TrendingDown className="h-4 w-4 text-red-400" />Albert’s Call · Why it could go down</h3>
              <p className="text-[11px] text-slate-500">Albert’s read of the downside risks</p>
            </div>
          </div>
          <ul className="space-y-2">{d.factors.risk.map((t, i) => <li key={i} className="flex gap-2 text-sm text-slate-300"><X className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />{t}</li>)}</ul>
        </Card>
      </div>
    </div>
  );
}

function AnalysisSection({ d }) {
  const isUp = d.signal === 'UP';
  return (
    <div className="space-y-5">
      <SectionHead icon={BarChart3} title="Quant Analysis" blurb={SECTIONS[2].blurb} />
      <AiReview text={reviewAnalysis(d)} section="analysis" />

      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <h3 className="mb-4 font-semibold text-slate-100">Quant Score Breakdown</h3>
        <div className="space-y-3">
          {d.quant_breakdown.map((b) => (
            <div key={b.name} className={`rounded-lg border p-3 ${b.active ? 'border-slate-800 bg-slate-950/40' : 'border-slate-800/50 bg-slate-950/20 opacity-60'}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-200">{b.name}</span>
                  {!b.active && <Lock className="h-3 w-3 text-slate-500" />}
                  <span className={`text-xs ${b.active ? signalText(b.signal) : 'text-slate-500'}`}>{b.signal}</span>
                </div>
                <span className="text-sm font-bold text-white">{b.score != null ? `${b.score}/100` : '—'}<span className="ml-1 text-[10px] text-slate-500">{b.active ? `w${b.weight}%` : ''}</span></span>
              </div>
              {b.active && (
                <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                  <div className="h-full rounded-full" style={{ width: `${b.score}%`, backgroundColor: scoreColor(b.score) }} />
                </div>
              )}
              <p className="mt-1.5 text-xs text-slate-500">{b.note}</p>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <div className="mb-4 flex items-center gap-2"><Gauge className="h-5 w-5 text-slate-400" /><h3 className="font-semibold text-slate-100">Live Feature Matrix</h3></div>
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
          <div className="mb-4 flex items-center gap-2"><BarChart3 className="h-5 w-5 text-slate-400" /><h3 className="font-semibold text-slate-100">Feature Importance</h3></div>
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className={`border-0 p-5 ring-1 lg:col-span-1 ${isUp ? 'bg-gradient-to-br from-emerald-500/15 to-slate-900 ring-emerald-500/30' : 'bg-gradient-to-br from-red-500/15 to-slate-900 ring-red-500/30'}`}>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Next-Day Signal · {d.as_of}</p>
          <div className="mt-2 flex items-center gap-2">
            {isUp ? <TrendingUp className="h-8 w-8 text-emerald-400" /> : <TrendingDown className="h-8 w-8 text-red-400" />}
            <span className={`text-3xl font-black ${isUp ? 'text-emerald-400' : 'text-red-400'}`}>{d.signal}</span>
            <span className="ml-auto text-2xl font-bold text-white">{d.confidence}%</span>
          </div>
          <p className="mt-2 text-xs text-slate-500">P(Up) {d.prob_up}% · P(Down) {d.prob_down}% · predicts {d.predict_for_date}</p>
        </Card>
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800 lg:col-span-2">
          <div className="mb-3 flex items-center gap-2"><Waves className="h-5 w-5 text-slate-400" /><h3 className="font-semibold text-slate-100">TimeSeriesSplit Cross-Validation</h3><span className="text-xs text-slate-500">(no future leakage)</span></div>
          <div className="grid grid-cols-5 gap-2">
            {d.cv_folds.map((f) => (
              <div key={f.fold} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-center">
                <p className="text-[11px] text-slate-400">Fold {f.fold}</p>
                <p className="mt-1 text-lg font-bold text-sky-400">{f.accuracy}%</p>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function PerformanceSection({ d }) {
  const sb = d.scoreboard;
  return (
    <div className="space-y-5">
      <SectionHead icon={Trophy} title="Performance" blurb={SECTIONS[3].blurb} coin={d.symbol || 'BTC'} />
      <AiReview text={reviewPerformance(d)} section="performance" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="border-0 bg-gradient-to-br from-sky-500/10 to-slate-900 p-6 ring-1 ring-slate-800">
          <div className="mb-2 flex items-center gap-2"><Trophy className="h-5 w-5 text-amber-400" /><h3 className="flex items-center gap-1 font-semibold text-slate-100">AI Scoreboard<InfoTip below text="The model's real out-of-sample track record: win rate, wins vs losses, and current streak across all graded past predictions." /></h3></div>
          <p className="text-xs text-slate-400">Real out-of-sample record · {sb.total} predictions graded</p>
          <div className="mt-3 flex items-end gap-2"><span className="text-5xl font-black text-sky-400">{sb.winRate}%</span><span className="mb-1 text-sm text-slate-400">win rate</span></div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-lg bg-emerald-500/10 p-2"><p className="text-[11px] text-slate-400">Wins</p><p className="text-lg font-bold text-emerald-400">{sb.wins}</p></div>
            <div className="rounded-lg bg-red-500/10 p-2"><p className="text-[11px] text-slate-400">Losses</p><p className="text-lg font-bold text-red-400">{sb.losses}</p></div>
            <div className="rounded-lg bg-slate-800/60 p-2"><p className="text-[11px] text-slate-400">Streak</p><p className={`text-lg font-bold ${sb.currentStreak >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{sb.currentStreak >= 0 ? `${sb.currentStreak}W` : `${Math.abs(sb.currentStreak)}L`}</p></div>
          </div>
          <div className="mt-4 flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
            <Radio className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
            <div className="text-xs text-slate-400"><span className="font-semibold text-slate-200">Live forward record:</span> {d.live_record.tracked} tracked · {d.live_record.resolved} resolved{d.live_record.winRate != null ? ` · ${d.live_record.winRate}% hit` : ' · grading begins on the next daily candle'}</div>
          </div>
        </Card>

        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800 lg:col-span-2">
          <div className="mb-3 flex items-center gap-2"><History className="h-5 w-5 text-slate-400" /><h3 className="flex items-center gap-1 font-semibold text-slate-100">Trade Log<InfoTip below text="Every recent prediction the model made, graded against what actually happened on the next candle — its date, signal, confidence and win/loss." /></h3><span className="text-sm text-slate-500">last {d.trades.length} graded predictions</span></div>
          <div className="max-h-[300px] overflow-y-auto pr-1">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-900 text-left text-xs uppercase tracking-wider text-slate-500">
                <tr><th className="py-2">Date</th><th className="py-2">Signal</th><th className="py-2 text-right">Conf.</th><th className="hidden py-2 text-right sm:table-cell">Close → Next</th><th className="py-2 text-right">Result</th></tr>
              </thead>
              <tbody>
                {d.trades.map((t, i) => (
                  <tr key={i} className="border-t border-slate-800/60">
                    <td className="py-2 font-mono text-xs text-slate-400">{t.date}</td>
                    <td className="py-2"><span className={`inline-flex items-center gap-1 font-semibold ${t.signal === 'UP' ? 'text-emerald-400' : 'text-red-400'}`}>{t.signal === 'UP' ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}{t.signal}</span></td>
                    <td className="py-2 text-right font-mono text-slate-300">{t.confidence}%</td>
                    <td className="hidden py-2 text-right font-mono text-xs text-slate-400 sm:table-cell">{fmtUsd(t.close)} → {fmtUsd(t.nextClose)}</td>
                    <td className="py-2 text-right">{t.correct ? <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-bold text-emerald-400"><Check className="h-3 w-3" />WIN</span> : <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-bold text-red-400"><X className="h-3 w-3" />LOSS</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <div className="mb-4"><h3 className="flex items-center gap-1 font-semibold text-slate-100">AI Accuracy vs {(d.symbol || 'BTC')} Price<InfoTip below text={`The model's 30-day rolling hit-rate (right axis) plotted against ${(d.symbol || 'BTC')} spot price (left axis), so you can see how accuracy held up through different market conditions.`} /></h3><p className="text-sm text-slate-400">30-day rolling accuracy against spot price · {d.first_date} → {d.as_of}</p></div>
        <div className="h-[380px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={d.performance} margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
              <defs><linearGradient id="btcFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#94a3b8" stopOpacity={0.25} /><stop offset="100%" stopColor="#94a3b8" stopOpacity={0.02} /></linearGradient></defs>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickLine={false} minTickGap={40} />
              <YAxis yAxisId="left" orientation="left" stroke="#94a3b8" fontSize={11} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} tickLine={false} domain={['auto', 'auto']} />
              <YAxis yAxisId="right" orientation="right" stroke="#38bdf8" fontSize={11} tickFormatter={(v) => `${v}%`} tickLine={false} domain={[30, 90]} />
              <Tooltip content={<ChartTooltip />} />
              <Legend verticalAlign="top" height={30} wrapperStyle={{ fontSize: 13 }} />
              <Area yAxisId="left" name={`${(d.symbol || 'BTC')} Price`} type="monotone" dataKey="btcPrice" stroke="#94a3b8" strokeWidth={1.5} fill="url(#btcFill)" />
              <Line yAxisId="right" name="AI Accuracy" type="monotone" dataKey="aiAccuracy" stroke="#38bdf8" strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}

function ComingSoonSection({ section }) {
  const Icon = section.icon;
  return (
    <div className="space-y-5">
      <SectionHead icon={Icon} title={section.label} blurb={section.blurb} />
      <Card className="flex flex-col items-center justify-center gap-4 border-0 bg-slate-900 p-16 ring-1 ring-slate-800">
        <div className="rounded-full bg-slate-800 p-4"><Icon className="h-8 w-8 text-sky-400" /></div>
        <h3 className="text-xl font-bold text-white">{section.label} is coming soon</h3>
        <p className="max-w-md text-center text-sm text-slate-400">This section is on the roadmap. The core intelligence engine (score, regime, forecasts, performance) is live now — this builds on top of it.</p>
        <Badge variant="outline" className="border-slate-700 text-slate-400">Roadmap</Badge>
      </Card>
    </div>
  );
}

function MarketIntelCard({ d }) {
  const mi = d.market_intel; if (!mi) return null;
  const rows = [
    ['Overall Quant Score', `${mi.quant_score} — ${mi.quant_label}`],
    ['Market Regime', mi.regime],
    ['24h Higher Probability', mi.higher_24h != null ? `${mi.higher_24h}%` : 'n/a'],
    ['7d Higher Probability', mi.higher_7d != null ? `${mi.higher_7d}%` : 'n/a'],
    ['Model Confidence', mi.confidence],
    ['Technical Structure', mi.technical_structure],
    ['BTC Dominance', mi.dominance],
    ['Cycle Phase', mi.cycle_phase],
    ['Smart Money', mi.smart_money],
    ['Exchange Supply', mi.exchange_supply],
    ['Pressure Map', mi.pressure_map],
    ['Derivatives Risk', mi.derivatives_risk],
    ['Crowd Intelligence', mi.crowd],
    ['Social Hype Risk', mi.hype_risk],
  ];
  return (
    <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
      <div className="mb-4 flex items-center gap-2"><Landmark className="h-5 w-5 text-sky-400" /><h3 className="font-semibold text-slate-100">Market Intelligence</h3></div>
      <div className="grid grid-cols-1 gap-x-8 gap-y-1.5 md:grid-cols-2">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between border-b border-slate-800/50 py-1.5 text-sm">
            <span className="text-slate-400">{k}</span>
            <span className={`text-right font-medium ${String(v).startsWith('Awaiting') ? 'text-slate-600' : 'text-slate-100'}`}>{v}</span>
          </div>
        ))}
      </div>
      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3"><p className="text-[11px] font-semibold uppercase text-emerald-400">Primary Tailwind</p><p className="mt-1 text-sm text-slate-300">{mi.top_positive}</p></div>
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3"><p className="text-[11px] font-semibold uppercase text-red-400">Primary Risk</p><p className="mt-1 text-sm text-slate-300">{mi.top_risk}</p></div>
      </div>
    </Card>
  );
}

function CandleChart({ ohlc, sr }) {
  if (!ohlc || !ohlc.length) return null;
  const W = 780, H = 340, padL = 8, padR = 62, padT = 12, padB = 22;
  const srp = (sr || []).map((s) => s.price);
  const vals = ohlc.flatMap((d) => [d.h, d.l]).concat(srp).filter((v) => v != null);
  const min = Math.min(...vals), max = Math.max(...vals); const span = (max - min) || 1;
  const n = ohlc.length; const cw = (W - padL - padR) / n;
  const y = (v) => padT + (1 - (v - min) / span) * (H - padT - padB);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 360 }}>
      {(sr || []).map((s, i) => (
        <g key={i}>
          <line x1={padL} x2={W - padR} y1={y(s.price)} y2={y(s.price)} stroke={s.type === 'resistance' ? '#f87171' : '#34d399'} strokeDasharray="4 3" strokeWidth="1" opacity="0.45" />
          <text x={W - padR + 3} y={y(s.price) + 3} fill={s.type === 'resistance' ? '#f87171' : '#34d399'} fontSize="9">${(s.price / 1000).toFixed(1)}k</text>
        </g>
      ))}
      {ohlc.map((d, i) => {
        const x = padL + i * cw + cw / 2; const up = d.c >= d.o; const col = up ? '#34d399' : '#f87171';
        const yO = y(d.o), yC = y(d.c); const top = Math.min(yO, yC); const bh = Math.max(Math.abs(yC - yO), 1);
        return (
          <g key={i}>
            <line x1={x} x2={x} y1={y(d.h)} y2={y(d.l)} stroke={col} strokeWidth="1" />
            <rect x={x - Math.max(cw * 0.3, 1)} y={top} width={Math.max(cw * 0.6, 1.5)} height={bh} fill={col} />
          </g>
        );
      })}
    </svg>
  );
}

function ChartSection({ d }) {
  const c = d.chart;
  if (!c) return <ComingSoonSection section={sec('chart')} />;
  const p = c.predictive;
  const biasColor = (b) => b === 'Bullish' ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' : b === 'Bearish' ? 'text-red-400 border-red-500/30 bg-red-500/10' : 'text-slate-300 border-slate-700 bg-slate-800/40';
  return (
    <div className="space-y-5">
      <SectionHead icon={CandlestickChart} title="Chart Intelligence" blurb={sec('chart').blurb} />
      <AiReview text={reviewChart(d)} section="chart" />
      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="flex items-center gap-1 font-semibold text-slate-100">Daily Candles · Auto S/R<InfoTip below text={`The last 90 daily candles with automatically detected support (green) and resistance (red) — price levels where ${(d.symbol || 'BTC')} has repeatedly reacted.`} /></h3>
          <span className="text-xs text-slate-500">last 90 days · <span className="text-emerald-400">support</span> / <span className="text-red-400">resistance</span></span>
        </div>
        <CandleChart ohlc={c.ohlc} sr={c.sr_levels} />
      </Card>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800 lg:col-span-1">
          <h3 className="mb-3 flex items-center gap-1 font-semibold text-slate-100">Predictive Setup<InfoTip below text="The model's read on the most likely next chart move, with the odds of a breakout up, a breakdown, or continued consolidation." /></h3>
          <p className="mb-3 text-sm text-slate-400">{p.primary_setup}</p>
          <div className="space-y-2">
            {[['Breakout up', p.breakout_up, 'bg-emerald-400'], ['Breakdown', p.breakdown, 'bg-red-400'], ['Consolidation', p.consolidation, 'bg-slate-500']].map(([lbl, v, cls]) => (
              <div key={lbl}>
                <div className="flex justify-between text-xs"><span className="text-slate-400">{lbl}</span><span className="font-mono text-slate-200">{v}%</span></div>
                <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-800"><div className={`h-full ${cls}`} style={{ width: `${v}%` }} /></div>
              </div>
            ))}
          </div>
        </Card>
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800 lg:col-span-2">
          <h3 className="mb-3 flex items-center gap-1 font-semibold text-slate-100">Detected Signals<InfoTip below text="Chart patterns and technical triggers the engine has spotted right now (e.g. crossovers, breakouts, divergences) and what each one implies." /></h3>
          <div className="space-y-2">
            {c.signals.map((s, i) => (
              <div key={i} className="flex items-start gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                <span className={`shrink-0 rounded border px-2 py-0.5 text-[11px] font-semibold ${biasColor(s.bias)}`}>{s.bias}</span>
                <div><p className="text-sm font-medium text-slate-200">{s.type}</p><p className="text-xs text-slate-500">{s.detail}</p></div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function CycleSection({ d }) {
  const c = d.cycle, dom = d.dominance;
  return (
    <div className="space-y-5">
      <SectionHead icon={Globe} title="Cycle & Macro" blurb={sec('cycle').blurb} />
      <AiReview text={reviewCycle(d)} section="cycle" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {c && (
          <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
            <div className="mb-3 flex items-center gap-2"><Layers className="h-5 w-5 text-amber-400" /><h3 className="font-semibold text-slate-100">Halving Cycle</h3><InfoTip below text="Where we are in Bitcoin's ~4-year halving cycle — days since the last halving, the current block reward, and how this phase has historically shaped returns." /><Badge variant="outline" className="ml-auto border-slate-700 text-amber-400">{c.phase}</Badge></div>
            <div className="mb-4">
              <div className="flex justify-between text-xs text-slate-500"><span>Last halving {c.last_halving_date}</span><span>{c.cycle_progress_pct}% through cycle</span></div>
              <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-gradient-to-r from-amber-400 to-orange-500" style={{ width: `${c.cycle_progress_pct}%` }} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {[['Days since halving', c.days_since_halving], ['Block reward', `${c.reward} BTC`], ['Block height', c.block_height.toLocaleString()], ['Next halving in', `~${c.est_days_to_next} days`], ['Blocks to next', c.blocks_to_next.toLocaleString()], ['Since-halving perf', c.cycle_perf_pct != null ? `${c.cycle_perf_pct}%` : 'n/a']].map(([k, v]) => (
                <div key={k} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">{k}</p><p className="mt-0.5 font-bold text-white">{v}</p></div>
              ))}
            </div>
          </Card>
        )}
        {dom && (
          <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
            <div className="mb-3 flex items-center gap-2"><Compass className="h-5 w-5 text-sky-400" /><h3 className="font-semibold text-slate-100">BTC Dominance</h3><InfoTip below text="Bitcoin's share of the total crypto market cap. Rising dominance often means money favours BTC over altcoins; falling can signal 'alt season'." /><Badge variant="outline" className="ml-auto border-slate-700 text-sky-400">{dom.direction}</Badge></div>
            <div className="flex items-end gap-2"><span className="text-4xl font-black text-white">{dom.dominance}%</span><span className="mb-1 text-sm text-slate-400">of crypto market cap</span></div>
            <div className="mt-3 grid grid-cols-3 gap-3 text-center text-sm">
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">Total mcap</p><p className="mt-0.5 font-bold text-white">${dom.total_mcap_t}T</p></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">7d change</p><p className="mt-0.5 font-bold text-white">{dom.change_7d != null ? `${dom.change_7d}%` : '—'}</p></div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">30d change</p><p className="mt-0.5 font-bold text-white">{dom.change_30d != null ? `${dom.change_30d}%` : '—'}</p></div>
            </div>
            <p className="mt-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-400">{dom.interpretation}</p>
            {dom.change_7d == null && <p className="mt-2 text-[11px] text-slate-600">7d/30d changes build as daily snapshots accumulate ({dom.history_points} logged).</p>}
          </Card>
        )}
      </div>
    </div>
  );
}

function reviewPolicy(d) {
  const p = d.policy; if (!p) return 'Policy & liquidity data is being generated.';
  const cm = d.crossmarket || [];
  const strongest = [...cm].sort((a, b) => Math.abs(b.corr_30d || 0) - Math.abs(a.corr_30d || 0))[0];
  const nextEv = (p.calendar || [])[0];
  return `The Policy & Liquidity Score is ${p.score}/100 — ${p.label} — with a Global Liquidity Impulse of ${p.liquidity_impulse}/100 (${p.liquidity_state}). The dollar (DXY ${p.dxy}), 10Y yield (${p.y10}%) and VIX (${p.vix}) set the tone. ${strongest ? `Right now Bitcoin's tightest link is to ${strongest.asset} (30d corr ${strongest.corr_30d}, ${strongest.label}), so that market carries extra weight in the short-horizon models.` : ''} Tailwind: ${p.tailwind} Risk: ${p.risk}${nextEv ? ` Next major event: ${nextEv.event} (${nextEv.date}).` : ''}`;
}

const corrColor = (v) => v == null ? 'text-slate-500' : Math.abs(v) > 0.6 ? (v > 0 ? 'text-emerald-400' : 'text-red-400') : Math.abs(v) > 0.3 ? (v > 0 ? 'text-emerald-300' : 'text-red-300') : 'text-slate-400';
const stageColor = (n) => n >= 10 ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' : n >= 7 ? 'text-sky-400 border-sky-500/30 bg-sky-500/10' : 'text-amber-400 border-amber-500/30 bg-amber-500/10';

function PolicySection({ d }) {
  const p = d.policy; const cm = d.crossmarket || [];
  if (!p) return <ComingSoonSection section={sec('policy')} />;
  return (
    <div className="space-y-5">
      <SectionHead icon={Landmark} title="Policy & Liquidity" blurb={sec('policy').blurb} />
      <AiReview text={reviewPolicy(d)} section="policy" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="border-0 bg-gradient-to-br from-sky-500/10 to-slate-900 p-6 ring-1 ring-slate-800">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Policy & Liquidity Score</p>
          <div className="mt-2 flex items-end gap-2"><span className="text-5xl font-black" style={{ color: scoreColor(p.score) }}>{p.score}</span><span className="mb-1 text-sm text-slate-400">/ 100</span></div>
          <p className="mt-1 font-semibold" style={{ color: scoreColor(p.score) }}>{p.label}</p>
        </Card>
        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800 lg:col-span-2">
          <div className="flex items-center justify-between"><p className="text-xs font-medium uppercase tracking-wider text-slate-400">Global Liquidity Impulse</p><Badge variant="outline" className="border-slate-700 text-sky-400">{p.liquidity_state}</Badge></div>
          <div className="mt-2 h-3 w-full overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-gradient-to-r from-red-500 via-amber-400 to-emerald-400" style={{ width: `${p.liquidity_impulse}%` }} /></div>
          <div className="mt-4 grid grid-cols-3 gap-3 text-center text-sm">
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">US Dollar (DXY)</p><p className="mt-0.5 font-bold text-white">{p.dxy}</p><p className="text-[11px] text-slate-500">z {p.components.dxy_z}</p></div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">10Y Yield</p><p className="mt-0.5 font-bold text-white">{p.y10}%</p><p className="text-[11px] text-slate-500">z {p.components.y10_z}</p></div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">VIX</p><p className="mt-0.5 font-bold text-white">{p.vix}</p><p className="text-[11px] text-slate-500">z {p.components.vix_z}</p></div>
          </div>
        </Card>
      </div>

      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <h3 className="mb-3 flex flex-wrap items-center gap-1 font-semibold text-slate-100">Cross-Market Correlations <span className="text-sm font-normal text-slate-500">(rolling, vs BTC)</span><InfoTip below text="How closely BTC has moved with other markets (stocks, gold, the dollar) recently. A high correlation means that market's swings tend to drag BTC along." /></h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="py-2">Asset</th><th className="py-2 text-right">Price</th><th className="py-2 text-right">7d</th><th className="py-2 text-right">30d</th><th className="py-2 text-right">90d</th><th className="py-2 text-right">β 30d</th><th className="py-2 text-right">Relationship</th></tr></thead>
            <tbody>
              {cm.map((a) => (
                <tr key={a.asset} className="border-t border-slate-800/60">
                  <td className="py-2 font-medium text-slate-200">{a.asset}</td>
                  <td className="py-2 text-right font-mono text-slate-300">{a.price?.toLocaleString()}</td>
                  <td className={`py-2 text-right font-mono ${corrColor(a.corr_7d)}`}>{a.corr_7d ?? '—'}</td>
                  <td className={`py-2 text-right font-mono font-bold ${corrColor(a.corr_30d)}`}>{a.corr_30d ?? '—'}</td>
                  <td className={`py-2 text-right font-mono ${corrColor(a.corr_90d)}`}>{a.corr_90d ?? '—'}</td>
                  <td className="py-2 text-right font-mono text-slate-400">{a.beta_30d ?? '—'}</td>
                  <td className={`py-2 text-right text-xs font-semibold ${corrColor(a.corr_30d)}`}>{a.label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <h3 className="mb-3 flex items-center gap-1 font-semibold text-slate-100">Central-Bank Policy Rates<InfoTip below text="Key interest rates set by major central banks. Higher rates tend to pull money out of risk assets like Bitcoin; cuts tend to add fuel." /></h3>
          <div className="space-y-1.5">
            {p.central_banks.map((b) => (
              <div key={b.bank} className="flex items-center justify-between border-b border-slate-800/50 py-1.5 text-sm">
                <span className="text-slate-300">{b.bank}</span>
                <span className="flex items-center gap-2"><span className="font-mono text-white">{b.rate}</span><span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${b.last === 'Cut' ? 'bg-emerald-500/10 text-emerald-400' : b.last === 'Hike' ? 'bg-red-500/10 text-red-400' : 'bg-slate-800 text-slate-400'}`}>{b.last}</span></span>
              </div>
            ))}
          </div>
        </Card>
        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <h3 className="mb-3 flex items-center gap-1 font-semibold text-slate-100">Policy Event Calendar<InfoTip below text="Upcoming macro events (rate decisions, inflation prints, jobs data) that can move markets — and Bitcoin along with them." /></h3>
          <div className="space-y-2">
            {p.calendar.map((e, i) => (
              <div key={i} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                <div><p className="text-sm font-medium text-slate-200">{e.event}</p><p className="text-xs text-slate-500">{e.date} · BTC sensitivity {e.btc_sensitivity}</p></div>
                <Badge variant="outline" className={`border-slate-700 ${e.importance === 'Very High' ? 'text-red-400' : 'text-amber-400'}`}>{e.importance}</Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <h3 className="mb-1 flex items-center gap-1 font-semibold text-slate-100">Regulation Tracker<InfoTip below text="A running list of notable crypto regulatory and policy developments, with a read on whether each is supportive or a headwind for BTC." /></h3>
        <p className="mb-3 text-xs text-slate-500">Proposal vs enacted vs implemented — 13-stage legal-status taxonomy (curated).</p>
        <div className="space-y-2">
          {p.regulation.map((r, i) => (
            <div key={i} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-slate-200">{r.title}</span>
                <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${stageColor(r.stage_num)}`}>{r.stage}</span>
                <span className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400">{r.jurisdiction}</span>
                <span className={`ml-auto text-xs font-semibold ${r.direction > 0 ? 'text-emerald-400' : r.direction < 0 ? 'text-red-400' : 'text-slate-400'}`}>{r.impact}</span>
              </div>
              <p className="mt-1.5 text-xs text-slate-500">{r.note}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3"><p className="text-[11px] font-semibold uppercase text-emerald-400">Primary Tailwind</p><p className="mt-1 text-sm text-slate-300">{p.tailwind}</p></div>
          <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3"><p className="text-[11px] font-semibold uppercase text-red-400">Primary Risk</p><p className="mt-1 text-sm text-slate-300">{p.risk}</p></div>
        </div>
        <p className="mt-3 text-sm text-slate-400"><span className="font-semibold text-slate-200">Interpretation:</span> {p.interpretation}</p>
      </Card>
    </div>
  );
}

function AlertsSection({ d, alertsData, onAck, filter = 'BTC', onFilter, coins = [] }) {
  const smart = (alertsData && alertsData.alerts) || [];
  const unseen = (alertsData && alertsData.unseen) || 0;
  const live = d.alerts || [];
  const filterCoins = ['ALL', 'BTC', ...coins.map((c) => c.symbol).filter((s) => s && s !== 'BTC')];
  const sevStyle = (s) => s === 'high' ? 'border-red-500/30 bg-red-500/5' : s === 'warning' ? 'border-amber-500/30 bg-amber-500/5' : s === 'success' ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-sky-500/25 bg-sky-500/5';
  const sevDot = (s) => s === 'high' ? 'bg-red-400' : s === 'warning' ? 'bg-amber-400' : s === 'success' ? 'bg-emerald-400' : 'bg-sky-400';
  const catStyle = (c) => ({ Regime: 'text-violet-300 bg-violet-500/10 border-violet-500/25',
    'Market State': 'text-sky-300 bg-sky-500/10 border-sky-500/25',
    'Quant Score': 'text-emerald-300 bg-emerald-500/10 border-emerald-500/25',
    'Data Trust': 'text-amber-300 bg-amber-500/10 border-amber-500/25',
    'Event Risk': 'text-orange-300 bg-orange-500/10 border-orange-500/25',
    Volatility: 'text-red-300 bg-red-500/10 border-red-500/25',
    News: 'text-violet-300 bg-violet-500/10 border-violet-500/25',
    Setup: 'text-amber-300 bg-amber-500/10 border-amber-500/25',
    Whale: 'text-cyan-300 bg-cyan-500/10 border-cyan-500/25' }[c] || 'text-slate-300 bg-slate-800/40 border-slate-700');
  const styleFor = (lvl) => lvl === 'danger' ? 'border-red-500/30 bg-red-500/5' : lvl === 'warning' ? 'border-amber-500/30 bg-amber-500/5' : lvl === 'success' ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-slate-800 bg-slate-950/40';
  const dot = (lvl) => lvl === 'danger' ? 'bg-red-400' : lvl === 'warning' ? 'bg-amber-400' : lvl === 'success' ? 'bg-emerald-400' : 'bg-sky-400';
  const fmtTs = (iso) => { try { return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); } catch { return iso; } };
  return (
    <div className="space-y-5">
      <SectionHead icon={Bell} title="Smart Alerts" blurb={sec('alerts').blurb} coin={d.symbol || 'BTC'} />
      <AiReview section="alerts" text="Albert is reviewing recent alerts…" voice />

      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-violet-400" />
          <h3 className="flex items-center gap-1 font-semibold text-slate-100">What Just Changed<InfoTip below text="The most recent shifts the engine flagged — new signals, regime changes or notable moves — so you can catch what's different since you last looked." /></h3>
          {unseen > 0 && <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-xs font-bold text-red-300 ring-1 ring-red-500/30">{unseen} new</span>}
          <span className="ml-auto text-xs text-slate-500">{smart.length} logged</span>
          {unseen > 0 && <Button size="sm" variant="outline" onClick={() => onAck && onAck()} className="h-7 gap-1.5 border-slate-700 text-xs text-slate-300 hover:bg-slate-800">Mark all read</Button>}
        </div>
        <div className="mb-4 flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Coin</span>
          {filterCoins.map((c) => (
            <button
              key={c}
              onClick={() => onFilter && onFilter(c)}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold transition ${filter === c ? 'border-sky-500/50 bg-sky-500/15 text-sky-200' : 'border-slate-700 bg-slate-800/40 text-slate-400 hover:bg-slate-800'}`}
            >
              {c !== 'ALL' && <CoinIcon symbol={c} size={14} />}
              {c === 'ALL' ? 'All Coins' : c}
            </button>
          ))}
        </div>
        <p className="mb-4 text-xs text-slate-500">State-change intelligence — non-price events triggered when the market regime, unified decision, data trust, quant score or event risk shifts between runs.</p>
        {smart.length === 0 ? (
          <p className="text-sm text-slate-500">No state changes logged{filter !== 'ALL' ? ` for ${filter}` : ''} yet. Alerts appear here automatically when the market’s regime, decision, trust or event risk changes.</p>
        ) : (
          <div className="space-y-2">
            {smart.map((a, i) => (
              <div key={a.id || i} className={`flex items-start gap-3 rounded-lg border p-3 ${sevStyle(a.severity)} ${!a.seen ? 'ring-1 ring-inset ring-sky-500/20' : ''}`}>
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${sevDot(a.severity)}`} />
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <CoinIcon symbol={a.symbol || 'BTC'} size={16} />
                    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${catStyle(a.category)}`}>{a.category}</span>
                    <span className="text-sm font-semibold text-slate-100">{a.title}</span>
                    {!a.seen && <span className="rounded-full bg-sky-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase text-sky-300">new</span>}
                    <span className="ml-auto text-[11px] text-slate-500">{fmtTs(a.ts)}</span>
                  </div>
                  <p className="mt-1 text-sm text-slate-400">{a.message}</p>
                  {a.link && <a href={a.link} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs font-semibold text-sky-400 hover:text-sky-300">Read source ↗</a>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <div className="mb-3 flex items-center gap-2"><Radio className="h-5 w-5 text-slate-400" /><h3 className="font-semibold text-slate-100">Current Market Read</h3><span className="text-sm text-slate-500">{live.length} active</span></div>
        <div className="space-y-2">
          {live.map((a, i) => (
            <div key={i} className={`flex items-start gap-3 rounded-lg border p-3 ${styleFor(a.level)}`}>
              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${dot(a.level)}`} />
              <div className="flex-1">
                <div className="flex items-center gap-2"><span className="text-sm font-semibold text-slate-200">{a.type}</span><span className="text-[11px] text-slate-500">{a.ts}</span></div>
                <p className="text-sm text-slate-400">{a.message}</p>
              </div>
            </div>
          ))}
          {live.length === 0 && <p className="text-sm text-slate-500">No active signals right now.</p>}
        </div>
        <p className="mt-4 text-[11px] text-slate-600">In-app feed (no email yet). Add a SendGrid key later to push these as email/push alerts.</p>
      </Card>
    </div>
  );
}

/* --------------------------- Time Machine ---------------------------- */
function ScenariosPanel() {
  const [scn, setScn] = React.useState(null);
  const [sel, setSel] = React.useState(0);
  const [selB, setSelB] = React.useState(1);
  const [compare, setCompare] = React.useState(false);
  React.useEffect(() => {
    fetch('/api/v1/scenarios', { cache: 'no-store' })
      .then((r) => r.json()).then((j) => { if (j.status === 'ready') setScn(j.scenarios.filter((s) => s.status === 'ready')); })
      .catch(() => {});
  }, []);
  if (!scn) return <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800"><p className="text-sm text-slate-500">Loading historic scenarios…</p></Card>;
  if (scn.length === 0) return null;
  const s = scn[sel] || scn[0];
  const win = (s.window || []).map((w) => ({ date: w.date, close: w.close, pick: w.is_pick ? w.close : null }));
  const outCol = (v) => v == null ? 'text-slate-400' : v >= 0 ? 'text-emerald-400' : 'text-red-400';
  const outTxt = (v) => v == null ? '—' : `${v >= 0 ? '+' : ''}${v}%`;

  // Rebase a scenario window to 100 at its event day, keyed by day-offset from the event
  const rebased = (scx) => {
    const w = scx.window || [];
    const pi = w.findIndex((p) => p.is_pick);
    const base = scx.price_at_event || (pi >= 0 ? w[pi].close : (w[0] && w[0].close)) || 1;
    const m = {};
    w.forEach((p, i) => { m[i - (pi < 0 ? 0 : pi)] = Math.round((p.close / base) * 1000) / 10; });
    return m;
  };
  const sB = scn[selB] || scn[(sel + 1) % scn.length];
  let overlay = [];
  if (compare) {
    const ma = rebased(s); const mb = rebased(sB);
    const offs = new Set([...Object.keys(ma), ...Object.keys(mb)].map(Number));
    overlay = Array.from(offs).filter((o) => o >= -60 && o <= 90).sort((x, y) => x - y)
      .map((o) => ({ off: o, a: ma[o] ?? null, b: mb[o] ?? null }));
  }

  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Sparkles className="h-4 w-4 text-amber-400" />
        <h3 className="text-sm font-semibold text-white">Famous Scenarios</h3>
        <span className="text-[11px] text-slate-500">point-in-time · real prices</span>
        <button onClick={() => setCompare(!compare)} className={`ml-auto rounded-full border px-3 py-1 text-xs font-semibold ${compare ? 'border-sky-400 bg-sky-500/15 text-sky-200' : 'border-slate-700 bg-slate-800/60 text-slate-300 hover:text-sky-300'}`}>{compare ? 'Comparing 2 ✓' : 'Compare two'}</button>
      </div>

      {!compare ? (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {scn.map((x, i) => (
              <button key={x.id} onClick={() => setSel(i)} className={`rounded-full border px-3 py-1.5 text-xs font-medium ${i === sel ? 'border-amber-500/40 bg-amber-500/10 text-amber-200' : 'border-slate-700 bg-slate-800/50 text-slate-400 hover:text-slate-200'}`}>{x.title}</button>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={win} margin={{ top: 10, right: 12, left: 4, bottom: 0 }}>
                    <defs><linearGradient id="scnFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#fbbf24" stopOpacity={0.25} /><stop offset="100%" stopColor="#fbbf24" stopOpacity={0} /></linearGradient></defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} minTickGap={40} />
                    <YAxis tick={{ fill: '#64748b', fontSize: 10 }} domain={['auto', 'auto']} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} width={48} />
                    <Tooltip content={<ChartTooltip />} />
                    <Area type="monotone" dataKey="close" stroke="#fbbf24" strokeWidth={2} fill="url(#scnFill)" name="BTC" />
                    <Scatter dataKey="pick" fill="#f59e0b" name="Event day" />
                    <ReferenceLine x={s.date} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: 'event', fill: '#f59e0b', fontSize: 10, position: 'top' }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wider text-amber-400">{s.category}</p>
              <h4 className="text-lg font-bold text-white">{s.title}</h4>
              <p className="text-xs text-slate-500">{s.date} · BTC {fmtUsd(s.price_at_event)}</p>
              <p className="mt-2 text-sm text-slate-400">{s.description}</p>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                {['30d', '90d', '365d'].map((k) => (
                  <div key={k} className="rounded-lg border border-slate-800 bg-slate-950/40 p-2">
                    <p className="text-[10px] uppercase text-slate-500">+{k}</p>
                    <p className={`text-sm font-bold ${outCol(s.outcomes[k])}`}>{outTxt(s.outcomes[k])}</p>
                  </div>
                ))}
              </div>
              {s.model?.available ? (
                <div className={`mt-3 rounded-lg border p-2.5 text-xs ${s.model.correct ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-300' : 'border-red-500/20 bg-red-500/5 text-red-300'}`}>
                  Model call: <span className="font-bold">{s.model.signal}</span> ({s.model.confidence}% conf) · actual {s.model.actual} · {s.model.correct ? 'correct' : 'missed'}
                </div>
              ) : (
                <p className="mt-3 rounded-lg border border-slate-800 bg-slate-950/40 p-2.5 text-[11px] text-slate-500">{s.model?.note}</p>
              )}
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wider text-amber-400">Scenario A</p>
              <select value={sel} onChange={(e) => setSel(Number(e.target.value))} className="w-full rounded-lg border border-slate-700 bg-slate-950/60 px-2 py-1.5 text-xs text-slate-200 focus:border-amber-500/50 focus:outline-none">
                {scn.map((x, i) => <option key={x.id} value={i}>{x.title} ({x.date})</option>)}
              </select>
            </div>
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wider text-sky-400">Scenario B</p>
              <select value={selB} onChange={(e) => setSelB(Number(e.target.value))} className="w-full rounded-lg border border-slate-700 bg-slate-950/60 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500/50 focus:outline-none">
                {scn.map((x, i) => <option key={x.id} value={i}>{x.title} ({x.date})</option>)}
              </select>
            </div>
          </div>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={overlay} margin={{ top: 10, right: 12, left: 4, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="off" tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}d`} />
                <YAxis tick={{ fill: '#64748b', fontSize: 10 }} domain={['auto', 'auto']} tickFormatter={(v) => `${v}`} width={40} />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }} formatter={(v, n) => [`${v} (=100 at event)`, n === 'a' ? s.title : sB.title]} labelFormatter={(l) => `${l > 0 ? '+' : ''}${l} days from event`} />
                <ReferenceLine x={0} stroke="#64748b" strokeDasharray="4 4" label={{ value: 'event', fill: '#94a3b8', fontSize: 10 }} />
                <ReferenceLine y={100} stroke="#334155" />
                <Line type="monotone" dataKey="a" stroke="#fbbf24" strokeWidth={2} dot={false} name="a" connectNulls />
                <Line type="monotone" dataKey="b" stroke="#38bdf8" strokeWidth={2} dot={false} name="b" connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex items-center justify-center gap-5 text-xs">
            <span className="flex items-center gap-1.5 text-amber-300"><span className="h-2 w-4 rounded bg-amber-400" />{s.title}</span>
            <span className="flex items-center gap-1.5 text-sky-300"><span className="h-2 w-4 rounded bg-sky-400" />{sB.title}</span>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-wider text-slate-500"><th className="pb-2">Metric</th><th className="pb-2 text-amber-300">{s.title}</th><th className="pb-2 text-sky-300">{sB.title}</th></tr></thead>
              <tbody>
                <tr className="border-t border-slate-800"><td className="py-2 text-slate-400">Event date</td><td className="py-2 text-slate-300">{s.date}</td><td className="py-2 text-slate-300">{sB.date}</td></tr>
                <tr className="border-t border-slate-800"><td className="py-2 text-slate-400">BTC at event</td><td className="py-2 text-slate-300">{fmtUsd(s.price_at_event)}</td><td className="py-2 text-slate-300">{fmtUsd(sB.price_at_event)}</td></tr>
                {['30d', '90d', '365d'].map((k) => (
                  <tr key={k} className="border-t border-slate-800">
                    <td className="py-2 text-slate-400">+{k} after</td>
                    <td className={`py-2 font-semibold ${outCol(s.outcomes[k])}`}>{outTxt(s.outcomes[k])}</td>
                    <td className={`py-2 font-semibold ${outCol(sB.outcomes[k])}`}>{outTxt(sB.outcomes[k])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p className="mt-3 text-[11px] text-slate-600">Prices are real (Yahoo/BTC-USD). In compare mode both paths are rebased to 100 at their event day so you can see how Bitcoin behaved relative to each event. Forward outcomes are revealed only after the event — never leaked into a prediction.</p>
    </Card>
  );
}

function TimeMachineSection() {
  const [rep, setRep] = React.useState(null);
  const [date, setDate] = React.useState('');
  const [loading, setLoading] = React.useState(true);
  const [range, setRange] = React.useState({ min: null, max: null });

  const fetchReplay = React.useCallback(async (dt) => {
    setLoading(true);
    try {
      const url = dt ? `/api/v1/replay?date=${dt}&window=30` : '/api/v1/replay?window=30';
      const r = await fetch(url, { cache: 'no-store' });
      const j = await r.json();
      if (j.status === 'ready') {
        setRep(j);
        if (j.min_date && j.max_date) setRange({ min: j.min_date, max: j.max_date });
        if (!dt && j.pick_date) setDate(j.pick_date);
      }
    } catch (e) { /* noop */ }
    setLoading(false);
  }, []);

  React.useEffect(() => { fetchReplay(); }, [fetchReplay]);

  const go = () => { if (date) fetchReplay(date); };
  const shift = (days) => {
    if (!date) return;
    const d = new Date(date + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() + days);
    let nd = d.toISOString().slice(0, 10);
    if (range.min && nd < range.min) nd = range.min;
    if (range.max && nd > range.max) nd = range.max;
    setDate(nd); fetchReplay(nd);
  };

  const win = (rep && rep.window) || [];
  const chartData = win.map((w) => ({ date: w.date, close: w.close, pick: w.is_pick ? w.close : null }));
  const correct = rep && rep.correct;

  return (
    <div className="space-y-5">
      <SectionHead icon={History} title="Bitcoin Time Machine" blurb={sec('timemachine').blurb} />
      <AiReview section="timemachine" text="Albert is reviewing the Time Machine…" voice />

      <ScenariosPanel />

      <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-[11px] uppercase tracking-wider text-slate-400">Replay date</label>
            <input type="date" value={date} min={range.min || undefined} max={range.max || undefined}
              onChange={(e) => setDate(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 focus:border-sky-500/50 focus:outline-none" />
          </div>
          <Button onClick={go} disabled={loading} className="gap-1.5 bg-sky-500 hover:bg-sky-400"><History className="h-4 w-4" />Replay this day</Button>
          <div className="flex gap-1.5">
            <Button size="sm" variant="outline" onClick={() => shift(-1)} className="border-slate-700 text-slate-300 hover:bg-slate-800">◀ Prev day</Button>
            <Button size="sm" variant="outline" onClick={() => shift(1)} className="border-slate-700 text-slate-300 hover:bg-slate-800">Next day ▶</Button>
          </div>
          {range.min && <span className="ml-auto text-[11px] text-slate-500">available {range.min} → {range.max} · {rep?.n} days</span>}
        </div>
      </Card>

      {loading && !rep ? (
        <Card className="border-0 bg-slate-900 p-10 text-center ring-1 ring-slate-800"><p className="text-sm text-slate-500">Loading replay…</p></Card>
      ) : rep && rep.status === 'ready' ? (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card className={`border-0 p-5 ring-1 ${correct ? 'bg-emerald-500/5 ring-emerald-500/25' : 'bg-red-500/5 ring-red-500/25'}`}>
              <p className="text-[11px] uppercase tracking-wider text-slate-400">Model call on {rep.pick_date}</p>
              <div className="mt-2 flex items-center gap-2">
                {rep.signal === 'UP' ? <ArrowUpRight className="h-7 w-7 text-emerald-400" /> : <ArrowDownRight className="h-7 w-7 text-red-400" />}
                <span className={`text-3xl font-black ${rep.signal === 'UP' ? 'text-emerald-400' : 'text-red-400'}`}>{rep.signal}</span>
                <span className="ml-1 rounded bg-slate-800 px-2 py-0.5 text-xs font-semibold text-slate-300">{rep.confidence}% conf</span>
              </div>
              <p className="mt-2 text-xs text-slate-500">Predicted next-day direction from {fmtUsd(rep.close)}</p>
            </Card>
            <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
              <p className="text-[11px] uppercase tracking-wider text-slate-400">What actually happened</p>
              <div className="mt-2 flex items-center gap-2">
                <span className={`text-3xl font-black ${rep.actual === 'UP' ? 'text-emerald-400' : 'text-red-400'}`}>{rep.actual}</span>
                <span className={`text-lg font-bold ${rep.move_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{rep.move_pct >= 0 ? '+' : ''}{rep.move_pct}%</span>
              </div>
              <p className="mt-2 text-xs text-slate-500">{fmtUsd(rep.close)} → {fmtUsd(rep.next_close)} next day</p>
            </Card>
            <Card className={`border-0 p-5 ring-1 ${correct ? 'bg-emerald-500/5 ring-emerald-500/25' : 'bg-red-500/5 ring-red-500/25'}`}>
              <p className="text-[11px] uppercase tracking-wider text-slate-400">Verdict</p>
              <div className="mt-2 flex items-center gap-2">
                {correct ? <Check className="h-7 w-7 text-emerald-400" /> : <X className="h-7 w-7 text-red-400" />}
                <span className={`text-3xl font-black ${correct ? 'text-emerald-400' : 'text-red-400'}`}>{correct ? 'Correct' : 'Missed'}</span>
              </div>
              {rep.rolling_accuracy != null && <p className="mt-2 text-xs text-slate-500">~{rep.rolling_accuracy}% accuracy in the surrounding 30 days</p>}
            </Card>
          </div>

          <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
            <h3 className="mb-3 text-sm font-semibold text-white">Price path around {rep.pick_date}</h3>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 10, right: 12, left: 4, bottom: 0 }}>
                  <defs>
                    <linearGradient id="tmFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.28} />
                      <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} minTickGap={40} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 10 }} domain={['auto', 'auto']} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} width={48} />
                  <Tooltip content={<ChartTooltip />} />
                  <Area type="monotone" dataKey="close" stroke="#38bdf8" strokeWidth={2} fill="url(#tmFill)" name="BTC" />
                  <Scatter dataKey="pick" fill="#fbbf24" name="Replay day" />
                  {rep.pick_date && <ReferenceLine x={rep.pick_date} stroke="#fbbf24" strokeDasharray="4 4" label={{ value: 'pick', fill: '#fbbf24', fontSize: 10, position: 'top' }} />}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-[11px] text-slate-600">Highlighted point is the replay day. The model saw only data up to that day when it made the call — no future leakage.</p>
          </Card>
        </>
      ) : (
        <Card className="border-0 bg-slate-900 p-10 text-center ring-1 ring-slate-800"><p className="text-sm text-slate-500">{rep?.message || 'Replay data is still being generated — hit Retrain, then try again.'}</p></Card>
      )}
    </div>
  );
}

const DIR_COLOR = {
  bullish: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10',
  bearish: 'text-red-400 border-red-500/30 bg-red-500/10',
  mixed: 'text-amber-400 border-amber-500/30 bg-amber-500/10',
  neutral: 'text-slate-400 border-slate-700 bg-slate-800/40',
};

function NewsCard({ c }) {
  const ai = c.ai || {};
  const dir = ai.direction || 'neutral';
  const th = ai.time_horizons || {};
  const fi = c.forecast_impact || {};
  const vBadge = c.verification === 'Confirmed' ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
    : c.verification === 'Unconfirmed' ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
    : 'border-slate-700 bg-slate-800/60 text-slate-300';
  const sources = c.sources && c.sources.length ? c.sources : [{ source: c.source, link: c.link, credibility: c.credibility }];
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded bg-slate-800 px-2 py-0.5 font-medium text-slate-300">{c.source}</span>
        {c.verification && <span className={`rounded border px-2 py-0.5 font-semibold ${vBadge}`}>{c.verification}</span>}
        {c.n_sources > 1 && <span className="rounded bg-slate-800/60 px-2 py-0.5 text-slate-400">{c.n_sources} sources</span>}
        <span className={`rounded border px-2 py-0.5 font-semibold uppercase ${DIR_COLOR[dir]}`}>{dir}</span>
        <span className="ml-auto rounded-full bg-sky-500/10 px-2 py-0.5 font-bold text-sky-400">Impact {c.impact} · {c.impact_label}</span>
      </div>
      <a href={c.link} target="_blank" rel="noreferrer" className="mt-2 block text-base font-semibold text-slate-100 hover:text-sky-300">{c.title}</a>
      <p className="mt-2 text-sm text-slate-300">{ai.summary}</p>
      {ai.why_it_matters && <p className="mt-2 text-sm text-slate-400"><span className="font-semibold text-slate-300">Why it matters: </span>{ai.why_it_matters}</p>}
      <div className="mt-3 flex items-center gap-1.5">
        <div className="flex h-2 flex-1 overflow-hidden rounded-full bg-slate-800">
          <div className="h-full bg-emerald-400" style={{ width: `${ai.bullish_pct || 0}%` }} />
          <div className="h-full bg-slate-500" style={{ width: `${ai.neutral_pct || 0}%` }} />
          <div className="h-full bg-red-400" style={{ width: `${ai.bearish_pct || 0}%` }} />
        </div>
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span className="text-emerald-400">▲ {ai.bullish_pct || 0}%</span><span>neutral {ai.neutral_pct || 0}%</span><span className="text-red-400">▼ {ai.bearish_pct || 0}%</span></div>
      {fi.note && (
        <div className={`mt-3 rounded-lg border p-2.5 text-xs ${fi.nudge_pts > 0 ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-300' : fi.nudge_pts < 0 ? 'border-red-500/20 bg-red-500/5 text-red-300' : 'border-slate-800 bg-slate-950/40 text-slate-400'}`}>
          <span className="font-semibold">Effect on BitMarkAI forecast: </span>{fi.note}{fi.horizons?.length ? ` (${fi.horizons.join(', ')})` : ''}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
        {th.immediate && <span className="rounded border border-slate-800 px-1.5 py-0.5 text-slate-400">Now: <span className={signalText(th.immediate === 'bullish' ? 'Bullish' : th.immediate === 'bearish' ? 'Bearish' : 'Neutral')}>{th.immediate}</span></span>}
        {th.seven_day && <span className="rounded border border-slate-800 px-1.5 py-0.5 text-slate-400">7d: {th.seven_day}</span>}
        {th.long_term && <span className="rounded border border-slate-800 px-1.5 py-0.5 text-slate-400">Long: {th.long_term}</span>}
        {(ai.categories || []).slice(0, 3).map((cat, i) => <span key={i} className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-400">{String(cat).replace(/_/g, ' ')}</span>)}
        {ai.confidence != null && <span className="ml-auto text-slate-500">confidence {Math.round((ai.confidence || 0) * 100)}%</span>}
      </div>
      {sources.length > 1 && (
        <div className="mt-3 border-t border-slate-800 pt-2">
          <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">Reported by {sources.length} sources</p>
          <div className="flex flex-wrap gap-2">
            {sources.map((s, i) => (
              <a key={i} href={s.link} target="_blank" rel="noreferrer" className="rounded bg-slate-800/60 px-2 py-0.5 text-[11px] text-slate-400 hover:text-sky-300">{s.source} ↗</a>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

function NewsSection({ news, status, onRefresh, refreshing }) {
  const [filter, setFilter] = React.useState('all');
  const symbol = React.useContext(SymbolContext);
  if (status !== 'ready' || !news) {
    return (
      <div className="space-y-5">
        <SectionHead icon={Newspaper} title={`${symbol} News`} blurb={sec('news').blurb} coin={symbol} />
        <Card className="flex items-center justify-center gap-3 border-0 bg-slate-900 p-16 ring-1 ring-slate-800">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-700 border-t-sky-400" />
          <span className="text-slate-400">{status === 'error' ? 'News engine error — try refresh.' : 'Gathering headlines & generating AI summaries…'}</span>
        </Card>
      </div>
    );
  }
  const b = news.briefing || {};
  const cards = (news.cards || []).filter((c) => filter === 'all' || (c.ai || {}).direction === filter);
  const biasColor = b.bias === 'Moderately Bullish' ? 'text-emerald-400' : b.bias === 'Moderately Bearish' ? 'text-red-400' : 'text-amber-400';
  return (
    <div className="space-y-5">
      <SectionHead icon={Newspaper} title={`${symbol} News`} blurb={sec('news').blurb} coin={symbol} />
      <AiReview section="news" text="Albert is reviewing today’s news…" voice />
      <Card className="border-0 bg-gradient-to-br from-violet-500/10 to-slate-900 p-6 ring-1 ring-violet-500/25">
        <div className="mb-3 flex items-center gap-2"><Sparkles className="h-5 w-5 text-violet-400" /><h3 className="flex items-center gap-1 font-semibold text-slate-100">Daily AI Briefing<InfoTip below text={`A plain-English summary of the day's most important ${symbol} news, written by the AI, with the likely market impact of each story.`} /></h3><span className="ml-auto text-[11px] text-slate-500">{news.model}</span></div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="rounded-lg bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">Market News Bias</p><p className={`text-lg font-bold ${biasColor}`}>{b.bias}</p></div>
          <div className="rounded-lg bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">Stories</p><p className="text-lg font-bold text-white">{b.total}</p></div>
          <div className="rounded-lg bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">High-Impact</p><p className="text-lg font-bold text-white">{b.major_stories}</p></div>
          <div className="rounded-lg bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">Next Event</p><p className="text-sm font-bold text-white">{b.next_event ? `${b.next_event.event}` : '—'}</p></div>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3"><p className="text-[11px] font-semibold uppercase text-emerald-400">Top Tailwind</p><p className="mt-1 text-sm text-slate-300">{b.top_tailwind}</p></div>
          <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3"><p className="text-[11px] font-semibold uppercase text-red-400">Top Risk</p><p className="mt-1 text-sm text-slate-300">{b.top_risk}</p></div>
        </div>
      </Card>
      <div className="flex flex-wrap items-center gap-2">
        {['all', 'bullish', 'bearish', 'mixed', 'neutral'].map((f) => (
          <button key={f} onClick={() => setFilter(f)} className={`rounded-lg px-3 py-1.5 text-xs font-medium capitalize ${filter === f ? 'bg-sky-500/15 text-sky-300' : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'}`}>{f}</button>
        ))}
        <Button onClick={onRefresh} disabled={refreshing} size="sm" className="ml-auto gap-2 bg-slate-800 text-slate-100 hover:bg-slate-700"><RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />Refresh</Button>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {cards.map((c, i) => <NewsCard key={i} c={c} />)}
      </div>
      {cards.length === 0 && <p className="text-sm text-slate-500">No stories match this filter.</p>}
    </div>
  );
}

/* ----------------------------- BitMarkAI ----------------------------- */
const bmConfColor = (c) => ({ High: 'text-emerald-400', Moderate: 'text-lime-400',
  Low: 'text-amber-400', 'Very Low': 'text-orange-400' }[c] || 'text-slate-400');
const bmVol = (v) => ({ 'Very High': ['bg-red-500', 100], High: ['bg-orange-500', 78],
  Elevated: ['bg-amber-500', 52], Low: ['bg-emerald-500', 26] }[v] || ['bg-slate-600', 40]);
const scenColor = (n) => ({ 'Adoption Expansion': 'text-emerald-400', 'Base Adoption': 'text-sky-400',
  'Restrictive Policy': 'text-amber-400', 'Severe Disruption': 'text-red-400' }[n] || 'text-slate-300');

function BmHorizonCard({ h }) {
  const up = h.prob_above >= 50;
  const [vc, vp] = bmVol(h.expected_volatility);
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="mb-2 flex items-center gap-1.5">
        <img src="/albert.png" alt="Albert" className="h-5 w-5 rounded-full object-cover ring-1 ring-sky-500/50" />
        <span className="text-[10px] font-bold uppercase tracking-wider text-sky-300">Albert’s Call</span>
      </div>
      <div className="flex items-center justify-between">
        <div><h3 className="text-base font-bold text-white">{h.label}</h3><p className="text-[11px] text-slate-500">{h.horizon} horizon</p></div>
        <Badge variant="outline" className={`border-slate-700 ${up ? 'text-emerald-400' : 'text-red-400'}`}>{up ? 'Leans Up' : 'Leans Down'}</Badge>
      </div>
      <div className="mt-3 flex justify-between text-sm font-semibold"><span className="text-emerald-400">Above {h.prob_above}%</span><span className="text-red-400">{h.prob_below}% Below</span></div>
      <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-red-500/40"><div className="h-full rounded-full bg-emerald-400" style={{ width: `${h.prob_above}%` }} /></div>
      <div className="mt-3 space-y-1.5 text-sm">
        <div className="flex justify-between"><span className="text-slate-500">Base case</span><span className="font-mono font-semibold text-slate-200">{fmtUsd(h.base_low)}–{fmtUsd(h.base_high)}</span></div>
        <div className="flex justify-between"><span className="text-emerald-400/70">Bull case</span><span className="font-mono text-emerald-400">{fmtUsd(h.bull_low)}–{fmtUsd(h.bull_high)}</span></div>
        <div className="flex justify-between"><span className="text-red-400/70">Bear case</span><span className="font-mono text-red-400">{fmtUsd(h.bear_low)}–{fmtUsd(h.bear_high)}</span></div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div><p className="text-slate-500">Expected volatility</p><div className="mt-1 flex items-center gap-1.5"><div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800"><div className={`h-full rounded-full ${vc}`} style={{ width: `${vp}%` }} /></div></div><p className="mt-0.5 text-slate-400">{h.expected_volatility}</p></div>
        <div><p className="text-slate-500">Model confidence</p><p className={`mt-1 font-bold ${bmConfColor(h.model_confidence)}`}>{h.model_confidence}</p>{h.accuracy != null && <p className="text-[10px] text-slate-500">backtest {h.accuracy}%</p>}</div>
      </div>
      <div className="mt-3 border-t border-slate-800 pt-2 text-xs">
        <p className="text-emerald-400/90">▲ {h.top_positive}</p>
        <p className="mt-1 text-red-400/90">▼ {h.top_risk}</p>
      </div>
      <div className="mt-3">
        <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">What drives this horizon</p>
        <div className="space-y-1">
          {h.weighting.slice(0, 4).map((w) => (
            <div key={w.category} className="flex items-center gap-2 text-[11px]">
              <span className="w-32 shrink-0 truncate text-slate-400">{w.category}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-gradient-to-r from-sky-500 to-violet-500" style={{ width: `${w.weight * 2}%` }} /></div>
              <span className="w-7 text-right font-mono text-slate-400">{w.weight}%</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function BmScenarioCard({ h }) {
  return (
    <Card className="border-0 bg-gradient-to-br from-violet-500/[0.06] to-slate-900 p-5 ring-1 ring-violet-500/20">
      <div className="mb-2 flex items-center gap-1.5">
        <img src="/albert.png" alt="Albert" className="h-5 w-5 rounded-full object-cover ring-1 ring-violet-500/50" />
        <span className="text-[10px] font-bold uppercase tracking-wider text-violet-300">Albert’s Call</span>
      </div>
      <div className="flex items-center justify-between">
        <div><h3 className="text-base font-bold text-white">{h.label}</h3><p className="text-[11px] text-slate-500">{h.horizon} · broad scenarios, not a single target</p></div>
        <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${bmConfColor(h.model_confidence)} border-slate-700`}>Confidence {h.model_confidence}</span>
      </div>
      <div className="mt-3 space-y-2.5">
        {h.scenarios.map((s) => (
          <div key={s.name}>
            <div className="flex items-center justify-between text-xs">
              <span className={`font-semibold ${scenColor(s.name)}`}>{s.name}</span>
              <span className="font-mono text-slate-300">{fmtUsd(s.low)}–{fmtUsd(s.high)} <span className="text-slate-500">· {s.prob}%</span></span>
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-800"><div className={`h-full rounded-full ${scenColor(s.name).replace('text-', 'bg-')}`} style={{ width: `${s.prob * 2.2}%` }} /></div>
            <p className="mt-0.5 text-[10px] text-slate-500">{s.note}</p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-slate-500">The further out the forecast, the wider the range and the lower the certainty.</p>
    </Card>
  );
}

function WhyChangedPanel({ bm }) {
  const [open, setOpen] = React.useState(null);
  const byName = {};
  (bm.horizons || []).forEach((h) => { byName[h.label] = h; byName[h.horizon] = h; });
  const changes = bm.changes || [];
  return (
    <Card className="border-0 bg-gradient-to-br from-sky-500/[0.06] to-slate-900 p-5 ring-1 ring-sky-500/20">
      <div className="mb-2 flex items-center gap-2.5">
        <img src="/albert.png" alt="Albert" className="h-8 w-8 rounded-full object-cover ring-2 ring-sky-500/40" />
        <h3 className="text-sm font-semibold text-white">Why the forecast changed</h3>
      </div>
      <p className="text-sm leading-relaxed text-slate-300">{bm.change_explanation}</p>
      {changes.length > 0 ? (
        <div className="mt-3 space-y-1.5">
          {changes.map((c, i) => {
            const h = byName[c.horizon];
            const isOpen = open === i;
            return (
              <div key={i} className="rounded-lg border border-slate-800 bg-slate-950/40">
                <button onClick={() => setOpen(isOpen ? null : i)} className="flex w-full items-center gap-3 p-2.5 text-left text-sm">
                  <span className="w-10 font-bold text-slate-200">{c.horizon}</span>
                  <span className="text-slate-400">prob. higher {c.from}% → {c.to}%</span>
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${c.prob_delta > 0 ? 'border-emerald-500/30 text-emerald-300' : c.prob_delta < 0 ? 'border-red-500/30 text-red-300' : 'border-slate-700 text-slate-400'}`}>{c.prob_delta > 0 ? '+' : ''}{c.prob_delta}pt</span>
                  <span className="ml-auto text-slate-500">{isOpen ? '▲' : '▼'}</span>
                </button>
                {isOpen && h && (
                  <div className="space-y-2 border-t border-slate-800 p-3 text-sm">
                    <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2.5"><p className="text-[10px] font-semibold uppercase text-emerald-400">Supporting factor</p><p className="mt-0.5 text-slate-300">{h.top_positive}</p></div>
                    <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-2.5"><p className="text-[10px] font-semibold uppercase text-red-400">Offsetting risk</p><p className="mt-0.5 text-slate-300">{h.top_risk}</p></div>
                    <p className="text-[11px] text-slate-500">Affects the <span className="font-semibold text-slate-300">{c.horizon}</span> horizon · confidence {h.model_confidence} · expected volatility {h.expected_volatility}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="mt-2 text-xs text-slate-500">No material change since the previous run — the drivers are steady.</p>
      )}
      <p className="mt-3 text-[11px] text-slate-600">Tap a horizon to see the strongest factor for and against it. Factors are the model’s current interpretation of live signals — not guaranteed causes.</p>
    </Card>
  );
}

function BitMarkSection({ d }) {
  const bm = d.bitmark;
  const [running, setRunning] = React.useState(false);
  const [runMsg, setRunMsg] = React.useState(null);
  if (!bm) return <ComingSoonSection section={sec('bitmark')} />;
  const trigLabel = { scheduled: 'Scheduled', manual: 'Manual run', event: 'Event-triggered' }[bm.trigger] || bm.trigger;
  const trigColor = bm.trigger === 'event' ? 'text-orange-300 border-orange-500/30' : bm.trigger === 'manual' ? 'text-sky-300 border-sky-500/30' : 'text-slate-300 border-slate-700';
  const models = bm.horizons.filter((h) => h.type === 'model');
  const scenarios = bm.horizons.filter((h) => h.type === 'scenario');
  const runForecast = async () => {
    if (running) return;
    setRunning(true); setRunMsg(null);
    const passcode = (typeof window !== 'undefined' && window.localStorage.getItem('btciq_admin_passcode')) || '';
    try {
      const r = await fetch('/api/v1/bitmark/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passcode }),
      });
      const j = await r.json();
      setRunMsg({ status: j.status, text: j.status === 'unauthorized' ? 'Admin passcode required — set it in Settings to run a manual forecast.' : j.message });
    } catch (e) { setRunMsg({ status: 'error', text: 'Could not start a forecast — please try again.' }); }
    finally { setRunning(false); }
  };
  return (
    <div className="space-y-5">
      <SectionHead icon={Sparkles} title="BitMarkAI" blurb={sec('bitmark').blurb} coin={d.symbol || 'BTC'} />

      <Card className="border-0 bg-gradient-to-br from-amber-500/[0.08] via-violet-500/[0.08] to-slate-900 p-6 ring-1 ring-amber-500/25">
        <div className="flex flex-wrap items-center gap-4">
          <div className="rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 p-2.5"><Sparkles className="h-6 w-6 text-white" /></div>
          <div>
            <h2 className="text-xl font-black text-white">BitMarkAI <span className="text-sm font-medium text-slate-400">Bitcoin Price Prediction Engine</span></h2>
            <p className="text-xs text-slate-400">Adaptive, probability-based forecasts · 1 week to 5 years · model {bm.model_version}</p>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-3">
            <div className="text-right text-xs">
              <span className={`rounded-full border px-2 py-0.5 font-semibold ${trigColor}`}>{trigLabel}</span>
              <p className="mt-1 text-slate-500">Issued {bm.issued} · next {bm.next_scheduled_update}</p>
            </div>
            <Button onClick={runForecast} disabled={running} className="gap-2 bg-gradient-to-r from-amber-500 to-orange-500 text-white shadow-lg shadow-amber-500/20 hover:from-amber-400 hover:to-orange-400">
              <RefreshCw className={`h-4 w-4 ${running ? 'animate-spin' : ''}`} />Run New Forecast
            </Button>
          </div>
        </div>
        {runMsg && (
          <div className={`mt-3 rounded-lg border p-3 text-sm ${runMsg.status === 'rate_limited' ? 'border-amber-500/30 bg-amber-500/10 text-amber-200' : runMsg.status === 'started' ? 'border-sky-500/30 bg-sky-500/10 text-sky-200' : 'border-slate-700 bg-slate-800/40 text-slate-300'}`}>{runMsg.text}</div>
        )}
      </Card>

      <WhyChangedPanel bm={bm} />

      <div>
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Model forecasts · 1 week to 1 year</p>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {models.map((h) => <BmHorizonCard key={h.horizon} h={h} />)}
        </div>
      </div>
      <div>
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Long-range scenarios · 2 & 5 years</p>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {scenarios.map((h) => <BmScenarioCard key={h.horizon} h={h} />)}
        </div>
      </div>
      <p className="text-center text-[11px] text-slate-600">BitMarkAI · powered by BitCentAI · probability-based research, not financial advice.</p>
    </div>
  );
}

/* ----------------- Prediction Ledger / Scorecard --------------------- */
const impColor = (i) => ({ 'Very High': 'text-red-400 border-red-500/30 bg-red-500/10',
  High: 'text-orange-400 border-orange-500/30 bg-orange-500/10',
  Medium: 'text-amber-400 border-amber-500/30 bg-amber-500/10',
  Low: 'text-slate-400 border-slate-700 bg-slate-800/40' }[i] || 'text-slate-400 border-slate-700');
const volColor = (v) => ({ 'Very High': 'bg-red-500', High: 'bg-orange-500',
  Elevated: 'bg-amber-500', Low: 'bg-emerald-500' }[v] || 'bg-slate-600');
const volPct = (v) => ({ 'Very High': 100, High: 78, Elevated: 52, Low: 26 }[v] || 40);
const feedColor = (s) => ({ live: 'text-emerald-400', degraded: 'text-amber-400',
  stale: 'text-orange-400', down: 'text-red-400' }[s] || 'text-slate-400');
const feedDot = (s) => ({ live: 'bg-emerald-400', degraded: 'bg-amber-400',
  stale: 'bg-orange-400', down: 'bg-red-400' }[s] || 'bg-slate-500');
function ageTxt(m) { if (m == null) return 'live'; if (m < 60) return `${m}m ago`; const h = Math.floor(m / 60); return h < 24 ? `${h}h ago` : `${Math.floor(h / 24)}d ago`; }
function countdown(dateStr) {
  const t = new Date(dateStr + 'T13:30:00Z').getTime() - Date.now();
  if (t <= 0) return 'now';
  const d = Math.floor(t / 86400000); const h = Math.floor((t % 86400000) / 3600000);
  return d > 0 ? `${d}d ${h}h` : `${h}h`;
}
const confBadge = (label) => ({
  High: 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10',
  Moderate: 'text-amber-300 border-amber-500/30 bg-amber-500/10',
  Low: 'text-slate-300 border-slate-700 bg-slate-800/50',
}[label] || 'text-slate-300 border-slate-700 bg-slate-800/50');

function Stat({ label, value, sub, color }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <p className="text-[11px] uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-1 text-3xl font-black" style={color ? { color } : undefined}>{value}</p>
      {sub && <p className="text-[11px] text-slate-500">{sub}</p>}
    </div>
  );
}

function LedgerExplorer({ ledger }) {
  const [fHz, setFHz] = React.useState('all');
  const [fOut, setFOut] = React.useState('all');
  const [fTrig, setFTrig] = React.useState('all');
  const [limit, setLimit] = React.useState(25);
  if (!ledger || ledger.length === 0) {
    return (
      <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
        <h3 className="mb-2 text-sm font-semibold text-white">Full Prediction Ledger</h3>
        <p className="text-sm text-slate-500">The ledger is still being built — issued forecasts will appear here with full filters.</p>
      </Card>
    );
  }
  const horizons = ['all', ...Array.from(new Set(ledger.map((x) => x.horizon).filter(Boolean)))];
  const triggers = ['all', ...Array.from(new Set(ledger.map((x) => x.trigger).filter(Boolean)))];
  const rows = ledger.filter((x) => {
    if (fHz !== 'all' && x.horizon !== fHz) return false;
    if (fTrig !== 'all' && x.trigger !== fTrig) return false;
    if (fOut === 'open' && x.resolved) return false;
    if (fOut === 'correct' && !(x.resolved && x.correct)) return false;
    if (fOut === 'incorrect' && !(x.resolved && x.correct === false)) return false;
    return true;
  });
  const Sel = ({ value, onChange, opts, label }) => (
    <label className="flex items-center gap-1.5 text-xs text-slate-400">
      {label}
      <select value={value} onChange={(e) => { onChange(e.target.value); setLimit(25); }}
        className="rounded-md border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs text-slate-200 focus:border-sky-500/50 focus:outline-none">
        {opts.map((o) => <option key={o} value={o}>{o === 'all' ? 'All' : o}</option>)}
      </select>
    </label>
  );
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold text-white">Full Prediction Ledger</h3>
        <span className="text-[11px] text-slate-500">{rows.length} of {ledger.length}</span>
        <div className="ml-auto flex flex-wrap gap-3">
          <Sel value={fHz} onChange={setFHz} opts={horizons} label="Horizon" />
          <Sel value={fOut} onChange={setFOut} opts={['all', 'open', 'correct', 'incorrect']} label="Outcome" />
          <Sel value={fTrig} onChange={setFTrig} opts={triggers} label="Trigger" />
        </div>
      </div>
      <div className="max-h-[520px] overflow-auto rounded-lg border border-slate-800">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-950/90 text-left uppercase tracking-wider text-slate-500">
            <tr>
              <th className="p-2">Issued</th><th className="p-2">Hz</th><th className="p-2">Dir</th>
              <th className="p-2">Base</th><th className="p-2">Conf</th><th className="p-2">Trigger</th>
              <th className="p-2">Regime</th><th className="p-2">Outcome</th><th className="p-2">Err</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((x, i) => (
              <tr key={i} className="border-t border-slate-800/70 hover:bg-slate-800/30">
                <td className="p-2 text-slate-400">{x.issued_date || '—'}</td>
                <td className="p-2 font-semibold text-slate-200">{x.horizon}</td>
                <td className={`p-2 font-semibold ${x.direction === 'UP' ? 'text-emerald-400' : 'text-red-400'}`}>{x.direction === 'UP' ? '▲' : '▼'} {x.prob_higher != null ? `${x.direction === 'UP' ? x.prob_higher : (100 - x.prob_higher)}%` : ''}</td>
                <td className="p-2 text-slate-300">{x.base != null ? fmtUsd(x.base) : '—'}</td>
                <td className="p-2 text-slate-400">{x.confidence || '—'}{x.confidence_pct != null ? ` ${Math.round(x.confidence_pct)}%` : ''}</td>
                <td className="p-2 text-slate-500">{x.trigger}</td>
                <td className="p-2 text-slate-500">{x.regime || '—'}</td>
                <td className="p-2">{!x.resolved ? <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-amber-300">open</span> : x.correct ? <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-emerald-300">correct</span> : <span className="rounded bg-red-500/10 px-1.5 py-0.5 text-red-300">missed</span>}</td>
                <td className="p-2 text-slate-400">{x.abs_pct_error != null ? `${x.abs_pct_error}%` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > limit && (
        <button onClick={() => setLimit(limit + 50)} className="mt-3 w-full rounded-lg border border-slate-700 py-2 text-xs text-slate-300 hover:bg-slate-800">Show more ({rows.length - limit} remaining)</button>
      )}
      <p className="mt-3 text-[11px] text-slate-600">Every forecast — winning and losing — is kept permanently. "Trigger" shows how it was issued (scheduled / manual / event / backtest walk-forward).</p>
    </Card>
  );
}

function ScorecardSection({ d }) {
  const pl = d.prediction_ledger;
  const [sc, setSc] = React.useState(null);
  const [modal, setModal] = React.useState(null);
  React.useEffect(() => {
    let on = true;
    fetch('/api/v1/scorecard', { cache: 'no-store' })
      .then((r) => r.json()).then((j) => { if (on && j.status === 'ready') setSc(j); })
      .catch(() => {});
    return () => { on = false; };
  }, []);
  if (!pl) return <ComingSoonSection section={sec('scorecard')} />;
  const o = pl.overall;
  const accCol = o.accuracy == null ? undefined : scoreColor(o.accuracy);
  const byRegime = (sc && sc.by_regime) || {};
  return (
    <div className="space-y-5">
      <SectionHead icon={ClipboardList} title="Prediction Ledger" blurb={sec('scorecard').blurb} />
      <AiReview section="scorecard" text="Albert is reviewing the track record…" voice />
      <div className="rounded-xl border border-sky-500/20 bg-sky-500/[0.06] p-4 text-sm text-slate-300">
        <span className="font-semibold text-sky-300">Accountability by design.</span> Every forecast is written to the ledger the moment it is issued — before the outcome exists — then graded automatically when it matures. Model <span className="font-mono text-slate-200">{pl.model_version}</span> · <span className="text-slate-200">{pl.total_logged}</span> forecasts logged (<span className="text-slate-200">{pl.live_logged}</span> live-forward + <span className="text-slate-200">{pl.backtested}</span> walk-forward backtest).
      </div>
      {(() => {
        const metricInfo = {
          accuracy: {
            title: 'Directional Accuracy', value: o.accuracy == null ? '—' : `${o.accuracy}%`,
            body: [
              `This is how often my up/down call was correct — measured only on the ${o.n || 0} forecasts that have already matured and been graded, never on open ones.`,
              '50% is a coin flip, so anything meaningfully above 50% means there is a genuine directional edge. Because every call is written to the ledger before the outcome exists, this number can\'t be cherry-picked.',
              'Read it alongside sample size: a high accuracy over hundreds of graded calls is far more trustworthy than the same number over a handful.',
            ],
          },
          brier: {
            title: 'Brier Score', value: o.brier == null ? '—' : String(o.brier),
            body: [
              'The Brier score grades how honest my probabilities are, not just the direction. It compares the confidence I stated (e.g. "70% up") against what actually happened.',
              '0.0 is perfect, 0.25 is what a lazy 50/50 guess scores — so lower is better. It punishes me for being confidently wrong more than for being cautiously wrong.',
              'A low accuracy but low Brier means I hedge well; high accuracy with a poor Brier means I\'m right but over-confident on the misses.',
            ],
          },
          mae: {
            title: 'Mean Absolute Error', value: o.mae_pct == null ? '—' : `${o.mae_pct}%`,
            body: [
              'This is the average gap between my base-case price target and where price actually landed, in percent.',
              'Smaller is better: a 2% MAE means my central price estimate was, on average, within 2% of reality.',
              'It measures magnitude, not direction — pair it with directional accuracy to see the full picture of how precise the forecasts are.',
            ],
          },
          range: {
            title: 'Range Hit Rate', value: o.range_hit_pct == null ? '—' : `${o.range_hit_pct}%`,
            body: [
              'Every forecast quotes a base range, not just a point. This is how often the actual close finished inside that range.',
              'A well-calibrated range should be hit roughly as often as its stated confidence — too low means my ranges are too tight, too high means they\'re too wide to be useful.',
              'It\'s the honesty check on the uncertainty bands you see on the forecast cards.',
            ],
          },
        };
        const cards = [
          ['accuracy', 'Directional Accuracy', o.accuracy == null ? '—' : `${o.accuracy}%`, `${o.n} graded`, accCol],
          ['brier', 'Brier Score', o.brier == null ? '—' : o.brier, 'lower is better (0 = perfect)', undefined],
          ['mae', 'Mean Abs. Error', o.mae_pct == null ? '—' : `${o.mae_pct}%`, 'base-case price vs actual', undefined],
          ['range', 'Range Hit Rate', o.range_hit_pct == null ? '—' : `${o.range_hit_pct}%`, 'actual inside base range', undefined],
        ];
        return (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {cards.map(([key, label, value, sub, color]) => (
                <button key={key} onClick={() => setModal(key)} className="group relative block w-full text-left transition hover:-translate-y-0.5">
                  <Stat label={label} value={value} sub={sub} color={color} />
                  <span className="absolute right-2 top-2 text-slate-500 group-hover:text-sky-300"><Info className="h-3.5 w-3.5" /></span>
                </button>
              ))}
            </div>
            {modal && (
              <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={() => setModal(null)}>
                <div className="w-full max-w-md rounded-xl border border-sky-500/25 bg-slate-900 p-5 shadow-2xl ring-1 ring-slate-800" onClick={(e) => e.stopPropagation()}>
                  <div className="mb-3 flex items-center gap-3">
                    <img src="/albert.png" alt="Albert" className="h-9 w-9 rounded-full object-cover ring-2 ring-sky-500/40" />
                    <div className="flex-1">
                      <h3 className="font-semibold text-white">{metricInfo[modal].title}</h3>
                      <p className="text-xs text-slate-400">Albert explains · current: <span className="font-mono text-sky-300">{metricInfo[modal].value}</span></p>
                    </div>
                    <button onClick={() => setModal(null)} className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"><X className="h-4 w-4" /></button>
                  </div>
                  <div className="space-y-2.5 text-sm leading-relaxed text-slate-300">
                    {metricInfo[modal].body.map((para, i) => <p key={i}>{para}</p>)}
                  </div>
                </div>
              </div>
            )}
          </>
        );
      })()}

      {Object.keys(byRegime).length > 0 && (
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <h3 className="mb-3 flex items-center gap-1 text-sm font-semibold text-white">Results by Market Regime<InfoTip below text="How the model's accuracy breaks down by market regime (trending, ranging, volatile) — so you can see the conditions where it's strongest or weakest." /></h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-wider text-slate-500">
                <th className="pb-2">Regime</th><th className="pb-2">Graded</th><th className="pb-2">Accuracy</th><th className="pb-2">Brier</th><th className="pb-2">MAE</th></tr></thead>
              <tbody>
                {Object.entries(byRegime).map(([rg, r]) => (
                  <tr key={rg} className="border-t border-slate-800">
                    <td className="py-2 font-semibold text-slate-200">{rg}</td>
                    <td className="py-2 text-slate-400">{r.n}</td>
                    <td className="py-2 font-bold" style={{ color: scoreColor(r.accuracy) }}>{r.accuracy}%</td>
                    <td className="py-2 text-slate-300">{r.brier ?? '—'}</td>
                    <td className="py-2 text-slate-300">{r.mae_pct == null ? '—' : `${r.mae_pct}%`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {Object.keys(pl.by_horizon).length > 0 && (
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <h3 className="mb-3 flex items-center gap-1 text-sm font-semibold text-white">Results by Forecast Horizon<InfoTip below text="Accuracy split by how far ahead the call looked (24h, 7d, 30d…). Shorter horizons and longer ones can behave very differently." /></h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-wider text-slate-500">
                <th className="pb-2">Horizon</th><th className="pb-2">Graded</th><th className="pb-2">Accuracy</th><th className="pb-2">Brier</th><th className="pb-2">MAE</th><th className="pb-2">Range Hit</th></tr></thead>
              <tbody>
                {['24H', '7D', '30D', '3M', '6M', '1Y'].filter((h) => pl.by_horizon[h]).map((h) => {
                  const r = pl.by_horizon[h];
                  return (
                    <tr key={h} className="border-t border-slate-800">
                      <td className="py-2 font-semibold text-slate-200">{h}</td>
                      <td className="py-2 text-slate-400">{r.n}</td>
                      <td className="py-2 font-bold" style={{ color: scoreColor(r.accuracy) }}>{r.accuracy}%</td>
                      <td className="py-2 text-slate-300">{r.brier ?? '—'}</td>
                      <td className="py-2 text-slate-300">{r.mae_pct == null ? '—' : `${r.mae_pct}%`}</td>
                      <td className="py-2 text-slate-300">{r.range_hit_pct == null ? '—' : `${r.range_hit_pct}%`}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {pl.calibration?.length > 0 && (
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <h3 className="mb-1 flex items-center gap-1 text-sm font-semibold text-white">Probability Calibration<InfoTip below text="Checks whether the model's stated odds match reality — e.g. of all the times it said '70% up', did BTC actually rise about 70% of the time?" /></h3>
          <p className="mb-3 text-xs text-slate-500">Each dot is a bucket of forecasts: X = what the model predicted, Y = how often price actually rose. The closer to the dashed line, the better calibrated. Bubble size = number of forecasts.</p>
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart margin={{ top: 10, right: 20, bottom: 24, left: 0 }}>
              <CartesianGrid stroke="#1e293b" />
              <XAxis type="number" dataKey="avg_pred" domain={[0, 100]} name="Predicted" unit="%" tick={{ fill: '#94a3b8', fontSize: 11 }} label={{ value: 'Predicted probability of higher (%)', position: 'insideBottom', offset: -12, fill: '#64748b', fontSize: 11 }} />
              <YAxis type="number" dataKey="realised_up" domain={[0, 100]} name="Actual" unit="%" tick={{ fill: '#94a3b8', fontSize: 11 }} label={{ value: 'Actual up-rate (%)', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11 }} />
              <ZAxis type="number" dataKey="n" range={[80, 500]} name="samples" />
              <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 100, y: 100 }]} stroke="#64748b" strokeDasharray="5 5" ifOverflow="extendDomain" />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }} formatter={(v, n) => [`${v}${n === 'samples' ? '' : '%'}`, n]} />
              <Scatter data={pl.calibration}>
                {pl.calibration.map((c, i) => {
                  const err = Math.abs(c.avg_pred - c.realised_up);
                  return <Cell key={i} fill={err < 10 ? '#34d399' : err < 20 ? '#fbbf24' : '#f87171'} />;
                })}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
          <div className="mt-2 flex flex-wrap gap-4 text-[11px] text-slate-500">
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-400" />well calibrated (&lt;10pt)</span>
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-400" />slight drift</span>
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-400" />over/under-confident</span>
            <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-slate-500" style={{ borderTop: '2px dashed #64748b' }} />perfect calibration</span>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white"><CalendarClock className="h-4 w-4 text-amber-400" />Open Forecasts (awaiting outcome)</h3>
          {pl.pending.length === 0 ? <p className="text-sm text-slate-500">No open forecasts yet — they appear here the moment each run is issued.</p> : (
            <div className="space-y-2">
              {pl.pending.map((p, i) => (
                <div key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-slate-800 bg-slate-950/40 p-2.5 text-sm">
                  <span className="w-10 font-bold text-slate-200">{p.horizon}</span>
                  <span className={`font-semibold ${p.direction === 'UP' ? 'text-emerald-400' : 'text-red-400'}`}>{p.direction === 'UP' ? '▲' : '▼'} {fmtUsd(p.base)}</span>
                  {p.bear != null && p.bull != null && <span className="text-xs text-slate-500">range {fmtUsd(p.bear)}–{fmtUsd(p.bull)}</span>}
                  <span className="text-xs text-slate-500">from {fmtUsd(p.price_at_issue)}</span>
                  {p.confidence && (
                    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${confBadge(p.confidence)}`}>
                      {p.confidence} conf{p.confidence_pct != null ? ` · ${Math.round(p.confidence_pct)}%` : ''}
                    </span>
                  )}
                  <span className="ml-auto rounded bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-300">{countdown(p.target_date)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <h3 className="mb-3 text-sm font-semibold text-white">Recently Graded (live-forward)</h3>
          {pl.recent.length === 0 ? <p className="text-sm text-slate-500">The first live forecasts are still maturing — 24H results land tomorrow. The scorecard above already reflects the full walk-forward backtest.</p> : (
            <div className="space-y-2">
              {pl.recent.map((r, i) => (
                <div key={i} className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-2.5 text-sm">
                  {r.correct ? <Check className="h-4 w-4 text-emerald-400" /> : <X className="h-4 w-4 text-red-400" />}
                  <span className="w-10 font-bold text-slate-200">{r.horizon}</span>
                  <span className="text-slate-400">said {r.direction} {r.prob_higher}%</span>
                  <span className="ml-auto text-slate-500">actual {r.actual_direction}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <LedgerExplorer ledger={sc?.ledger} />
    </div>
  );
}

/* ------------------------- Data Trust Layer -------------------------- */
function DataTrustSection({ d }) {
  const h = d.data_health;
  if (!h) return <ComingSoonSection section={sec('trust')} />;
  const col = h.score >= 90 ? '#34d399' : h.score >= 75 ? '#a3e635' : h.score >= 55 ? '#fbbf24' : '#f87171';
  return (
    <div className="space-y-5">
      <SectionHead icon={ShieldCheck} title="Data Trust" blurb={sec('trust').blurb} />
      <Card className={`border-0 bg-gradient-to-br from-slate-900 to-slate-950 p-6 ring-1 ${h.faded ? 'ring-orange-500/40' : 'ring-emerald-500/25'}`}>
        <div className="flex flex-wrap items-center gap-6">
          <div>
            <p className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-slate-400">Overall Data Trust<InfoTip below text="A 0–100 score for how fresh and reliable the underlying data feeds are. When trust drops, the model automatically tones down its odds." /></p>
            <p className="text-5xl font-black" style={{ color: col }}>{h.score}</p>
            <p className="text-sm font-semibold" style={{ color: col }}>{h.level}</p>
          </div>
          <div className="flex gap-3">
            <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-4 py-2 text-center"><p className="text-xl font-bold text-emerald-400">{h.live}</p><p className="text-[10px] text-slate-500">live</p></div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-4 py-2 text-center"><p className="text-xl font-bold text-amber-400">{h.degraded}</p><p className="text-[10px] text-slate-500">delayed</p></div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-4 py-2 text-center"><p className="text-xl font-bold text-orange-400">{h.stale}</p><p className="text-[10px] text-slate-500">stale/down</p></div>
          </div>
          <div className={`ml-auto max-w-md rounded-lg border p-3 text-sm ${h.faded ? 'border-orange-500/30 bg-orange-500/10 text-orange-200' : 'border-emerald-500/20 bg-emerald-500/[0.06] text-emerald-200'}`}>
            {h.faded ? <ShieldAlert className="mb-1 h-4 w-4" /> : <ShieldCheck className="mb-1 h-4 w-4" />}{h.note}
          </div>
        </div>
      </Card>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {h.feeds.map((f) => (
          <Card key={f.id} className="border-0 bg-slate-900 p-4 ring-1 ring-slate-800">
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${feedDot(f.status)} ${f.status === 'live' ? 'animate-pulse' : ''}`} />
              <h3 className="font-semibold text-white">{f.label}</h3>
              <span className={`ml-auto text-xs font-bold uppercase ${feedColor(f.status)}`}>{f.status}</span>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
              <div><p className="text-slate-500">Provider</p><p className="font-medium text-slate-300">{f.provider}</p></div>
              <div><p className="text-slate-500">Freshness</p><p className="font-medium text-slate-300">{ageTxt(f.age_min)}</p></div>
              <div><p className="text-slate-500">Confidence</p><p className="font-medium text-slate-300">{f.confidence}%</p></div>
            </div>
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full" style={{ width: `${f.confidence}%`, backgroundColor: f.confidence >= 90 ? '#34d399' : f.confidence >= 70 ? '#fbbf24' : '#f87171' }} /></div>
            <p className="mt-2 text-[11px] leading-relaxed text-slate-500">{f.methodology}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}

/* ------------------------- Event Calendar ---------------------------- */
const catColor = (c) => ({ Macro: 'text-sky-400 border-sky-500/30 bg-sky-500/10',
  Derivatives: 'text-violet-400 border-violet-500/30 bg-violet-500/10',
  'On-Chain': 'text-amber-400 border-amber-500/30 bg-amber-500/10',
  Regulatory: 'text-red-400 border-red-500/30 bg-red-500/10' }[c] || 'text-slate-400 border-slate-700');

function EventsSection({ d }) {
  const ec = d.event_calendar;
  if (!ec) return <ComingSoonSection section={sec('events')} />;
  const nx = ec.next_high_impact;
  return (
    <div className="space-y-5">
      <SectionHead icon={CalendarClock} title="Event Calendar" blurb={sec('events').blurb} />
      <AiReview section="events" text="Albert is reviewing the event calendar…" voice />
      {nx && (
        <Card className="border-0 bg-gradient-to-r from-orange-500/10 to-slate-900 p-5 ring-1 ring-orange-500/30">
          <div className="flex flex-wrap items-center gap-4">
            <div><p className="text-[11px] uppercase tracking-wider text-orange-300">Next high-impact event</p><p className="text-lg font-bold text-white">{nx.title}</p><p className="text-xs text-slate-400">{nx.description}</p></div>
            <div className="ml-auto text-center"><p className="text-3xl font-black text-orange-400">{countdown(nx.date)}</p><p className="text-[11px] text-slate-500">{nx.date}</p></div>
          </div>
        </Card>
      )}
      <div className="flex flex-wrap gap-2">
        {Object.entries(ec.counts).map(([c, n]) => (
          <span key={c} className={`rounded-full border px-3 py-1 text-xs font-medium ${catColor(c)}`}>{c} · {n}</span>
        ))}
        <span className="ml-auto text-xs text-slate-500">next {ec.window_days} days · {ec.events.length} events</span>
      </div>
      <div className="space-y-2">
        {ec.events.map((e, i) => (
          <Card key={i} className="border-0 bg-slate-900 p-4 ring-1 ring-slate-800">
            <div className="flex flex-wrap items-center gap-3">
              <div className="w-16 text-center">
                <p className="text-lg font-black text-white">{countdown(e.date)}</p>
                <p className="text-[10px] text-slate-500">{e.date.slice(5)}</p>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${catColor(e.category)}`}>{e.category}</span>
                  <span className="font-semibold text-white">{e.title}</span>
                  <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${impColor(e.importance)}`}>{e.importance}</span>
                </div>
                <p className="mt-0.5 text-xs text-slate-500">{e.description}</p>
              </div>
              <div className="w-28">
                <p className="text-[10px] uppercase tracking-wider text-slate-500">Exp. volatility</p>
                <div className="mt-1 flex items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800"><div className={`h-full rounded-full ${volColor(e.expected_volatility)}`} style={{ width: `${volPct(e.expected_volatility)}%` }} /></div>
                </div>
                <p className="mt-0.5 text-[10px] text-slate-400">{e.expected_volatility}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

/* ----------------------------- Ask Quant ----------------------------- */
function AskQuantSection({ d }) {
  const symbol = React.useContext(SymbolContext);
  const [sessionId] = React.useState(() => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2)));
  const [messages, setMessages] = React.useState([]);
  const [input, setInput] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const endRef = React.useRef(null);

  React.useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading]);

  const suggestions = [
    `Summarise the current ${symbol} market state in plain English.`,
    'Why did the forecast change?',
    `What is currently moving ${symbol}?`,
    'Which signal carries the greatest risk?',
    'What evidence contradicts the current forecast?',
    'What would invalidate the bullish outlook?',
    'Why is the model confidence only moderate?',
    'What is the difference between model confidence and data confidence?',
  ];

  const send = async (text) => {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', text: msg }]);
    setLoading(true);
    try {
      const r = await fetch('/api/v1/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: msg, symbol }),
      });
      const j = await r.json();
      setMessages((m) => [...m, { role: 'assistant', text: j.text || 'Sorry, I could not answer that just now.' }]);
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', text: 'Network error — please try again.' }]);
    } finally { setLoading(false); }
  };

  return (
    <div className="space-y-5">
      <SectionHead icon={MessageCircle} title="Ask Albert" blurb={sec('ask').blurb} />
      <AlbertIntroCard />
      <Card className="flex h-[560px] flex-col overflow-hidden border-0 bg-slate-900 p-0 ring-1 ring-slate-800">
        <div className="flex items-center gap-2.5 border-b border-slate-800 px-5 py-3">
          <img src="/albert.png" alt="Albert" className="h-9 w-9 rounded-full object-cover ring-2 ring-sky-500/40" />
          <div><p className="text-sm font-semibold text-white">Albert · BTCIQ HuCentAI Quant</p><p className="text-[10px] text-slate-500">Grounded in live dashboard data · Gemini 3 Flash</p></div>
          <span className="ml-auto flex items-center gap-1 text-[10px] font-bold text-emerald-400"><span className="h-2 w-2 rounded-full bg-emerald-400" />LIVE</span>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <img src="/albert.png" alt="Albert" className="h-20 w-20 rounded-full object-cover ring-2 ring-sky-500/40" />
              <div>
                <p className="font-semibold text-slate-200">Hi, I’m Albert — ask me anything about the market</p>
                <p className="mt-1 max-w-sm text-xs text-slate-500">I only use the live numbers on this dashboard — score, regime, forecasts, news, policy and cycle. I won’t invent data.</p>
              </div>
              <div className="flex max-w-lg flex-wrap justify-center gap-2">
                {suggestions.map((s, i) => (
                  <button key={i} onClick={() => send(s)} className="rounded-full border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs text-slate-300 hover:border-sky-500/40 hover:text-sky-300">{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex items-end gap-2 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {m.role === 'assistant' && <img src="/albert.png" alt="Albert" className="h-7 w-7 shrink-0 rounded-full object-cover ring-1 ring-sky-500/30" />}
              <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${m.role === 'user' ? 'bg-sky-500/15 text-sky-50 ring-1 ring-sky-500/25' : 'bg-slate-950/60 text-slate-200 ring-1 ring-slate-800'}`}>{m.text}</div>
            </div>
          ))}
          {loading && (
            <div className="flex items-end justify-start gap-2">
              <img src="/albert.png" alt="Albert" className="h-7 w-7 shrink-0 rounded-full object-cover ring-1 ring-sky-500/30" />
              <div className="flex items-center gap-1.5 rounded-2xl bg-slate-950/60 px-4 py-3 ring-1 ring-slate-800">
                <span className="h-2 w-2 animate-bounce rounded-full bg-sky-400" style={{ animationDelay: '0ms' }} />
                <span className="h-2 w-2 animate-bounce rounded-full bg-sky-400" style={{ animationDelay: '150ms' }} />
                <span className="h-2 w-2 animate-bounce rounded-full bg-sky-400" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          )}
          {!loading && messages.length > 0 && messages[messages.length - 1].role === 'assistant' && (
            <div className="flex flex-wrap gap-2 pl-9">
              {[
                ["Explain like I’m 5", "Explain your last answer like I’m 5 years old, in very simple plain words."],
                ["Give me the risks", "What are the main risks or things that could go wrong with what you just told me?"],
                ["What would change your mind?", "What would have to happen for your view to change?"],
                ["What do I watch next?", "In one or two lines, what key levels or signals should I watch next?"],
              ].map(([label, prompt]) => (
                <button key={label} onClick={() => send(prompt)} className="rounded-full border border-slate-700 bg-slate-800/50 px-3 py-1 text-[11px] font-medium text-slate-300 transition-colors hover:border-sky-500/40 hover:text-sky-300">{label}</button>
              ))}
            </div>
          )}
          <div ref={endRef} />
        </div>
        <div className="border-t border-slate-800 p-3">
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
              rows={1}
              placeholder="Ask Albert about the score, forecasts, news impact, risks…"
              className="max-h-32 flex-1 resize-none rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:border-sky-500/50 focus:outline-none"
            />
            <Button onClick={() => send()} disabled={loading || !input.trim()} className="gap-1.5 bg-sky-500 hover:bg-sky-400"><Send className="h-4 w-4" />Send</Button>
          </div>
          <p className="mt-2 text-center text-[10px] text-slate-600">Albert is an educational research assistant · not financial advice · grounded in live data but can still be imperfect.</p>
        </div>
      </Card>
    </div>
  );
}

// ---- Floating, screen-aware Ask Albert (present on every screen) ----
const SECTION_LABELS = {
  overview: 'all things BTCIQ', forecasts: 'Forecasts', 'market-intel': 'Market Intelligence',
  crossmarket: 'Cross-Market', analogs: 'Happening Again', smartmoney: 'Smart Money',
  whales: 'Whale Watch', institutional: 'Institutional & Derivatives', leverage: 'Leverage',
  macro: 'Macro & Policy', news: 'News', risk: 'Risk', events: 'Events',
  performance: 'Performance', timemachine: 'Time Machine', network: 'Network & Sentiment',
  dataaudit: 'Data Audit', admin: 'Admin', settings: 'Settings', alerts: 'Alerts',
};

function FloatingAlbert({ active, symbol, onExpand }) {
  const [open, setOpen] = React.useState(false);
  const [sessionId] = React.useState(() => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2)));
  const [messages, setMessages] = React.useState([]);
  const [input, setInput] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const endRef = React.useRef(null);
  const isOverview = !active || active === 'overview';
  const scopeLabel = SECTION_LABELS[active] || 'all things BTCIQ';

  React.useEffect(() => { if (open) endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading, open]);
  // Reset the mini-thread when the user switches screens so context stays relevant.
  React.useEffect(() => { setMessages([]); }, [active]);

  const suggestions = isOverview
    ? ['Give me the 10-second read on Bitcoin right now.', 'What is the biggest risk today?', "What's moving the market?"]
    : [`Give me a quick read on this ${scopeLabel} screen.`, `What should I watch on ${scopeLabel}?`, `What's the key signal here?`];

  const send = async (text) => {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', text: msg }]);
    setLoading(true);
    try {
      const r = await fetch('/api/v1/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: msg, symbol, section: active }),
      });
      const j = await r.json();
      setMessages((m) => [...m, { role: 'assistant', text: j.text || 'Sorry, I could not answer that just now.' }]);
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', text: 'Network error — please try again.' }]);
    } finally { setLoading(false); }
  };

  return (
    <>
      {/* Launcher */}
      {!open && (
        <button onClick={() => setOpen(true)} title="Ask Albert"
          className="fixed bottom-5 right-5 z-50 flex items-center gap-2 rounded-full border border-sky-500/40 bg-gradient-to-r from-sky-500 to-violet-600 py-2 pl-2 pr-4 text-white shadow-lg shadow-violet-500/30 transition-transform hover:scale-105">
          <img src="/albert.png" alt="Albert" className="h-8 w-8 rounded-full object-cover ring-2 ring-white/30" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
          <span className="text-sm font-semibold">Ask Albert</span>
        </button>
      )}
      {/* Panel */}
      {open && (
        <div className="fixed bottom-5 right-5 z-50 flex h-[540px] w-[92vw] max-w-[400px] flex-col overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl shadow-black/50 ring-1 ring-slate-800">
          <div className="flex items-center gap-2.5 border-b border-slate-800 bg-slate-950/60 px-4 py-3">
            <img src="/albert.png" alt="Albert" className="h-8 w-8 rounded-full object-cover ring-2 ring-sky-500/40" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-white">Ask Albert</p>
              <p className="truncate text-[10px] text-sky-400">{isOverview ? 'Talking about all things BTCIQ' : `Focused on: ${scopeLabel}`}</p>
            </div>
            {onExpand && <button onClick={() => { setOpen(false); onExpand(); }} title="Open full chat" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"><Maximize2 className="h-4 w-4" /></button>}
            <button onClick={() => setOpen(false)} title="Close" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"><X className="h-4 w-4" /></button>
          </div>
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {messages.length === 0 && (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
                <img src="/albert.png" alt="Albert" className="h-14 w-14 rounded-full object-cover ring-2 ring-sky-500/40" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                <p className="text-sm font-semibold text-slate-200">{isOverview ? "Hi, I'm Albert — ask me anything about Bitcoin" : `Ask me about the ${scopeLabel} screen`}</p>
                <p className="max-w-[16rem] text-[11px] text-slate-500">I only use the live dashboard numbers — I won't invent data.</p>
                <div className="flex flex-col gap-1.5">
                  {suggestions.map((s, i) => (
                    <button key={i} onClick={() => send(s)} className="rounded-full border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-[11px] text-slate-300 hover:border-sky-500/40 hover:text-sky-300">{s}</button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`flex items-end gap-2 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {m.role === 'assistant' && <img src="/albert.png" alt="Albert" className="h-6 w-6 shrink-0 rounded-full object-cover ring-1 ring-sky-500/30" onError={(e) => { e.currentTarget.style.display = 'none'; }} />}
                <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-[13px] leading-relaxed ${m.role === 'user' ? 'bg-sky-500/15 text-sky-50 ring-1 ring-sky-500/25' : 'bg-slate-950/60 text-slate-200 ring-1 ring-slate-800'}`}>{m.text}</div>
              </div>
            ))}
            {loading && (
              <div className="flex items-end justify-start gap-2">
                <img src="/albert.png" alt="Albert" className="h-6 w-6 shrink-0 rounded-full object-cover ring-1 ring-sky-500/30" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                <div className="flex items-center gap-1.5 rounded-2xl bg-slate-950/60 px-3 py-2.5 ring-1 ring-slate-800">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-sky-400" style={{ animationDelay: '0ms' }} />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-sky-400" style={{ animationDelay: '150ms' }} />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-sky-400" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
          <div className="border-t border-slate-800 p-2.5">
            <div className="flex items-end gap-2">
              <textarea value={input} onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                rows={1} placeholder={isOverview ? 'Ask about Bitcoin…' : `Ask about ${scopeLabel}…`}
                className="max-h-24 flex-1 resize-none rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-[13px] text-slate-100 placeholder-slate-500 focus:border-sky-500/50 focus:outline-none" />
              <Button onClick={() => send()} disabled={loading || !input.trim()} size="sm" className="bg-sky-500 hover:bg-sky-400"><Send className="h-4 w-4" /></Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}


// ---- Shareable Daily Report (clean exportable snapshot) ----
function DailyReportModal({ d, onClose }) {
  const cardRef = React.useRef(null);
  const [exporting, setExporting] = React.useState(false);
  const [cp] = useFetch('/api/v1/composite-price');
  const [fred] = useFetch('/api/v1/macro-fred');
  const [xa] = useFetch('/api/v1/cross-asset');
  const [ns] = useFetch('/api/v1/news-signals');

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


/* ---------------- Stage-1: Risk / Smart Money / Institutional / Settings --------------- */
function DemoBadge({ label = 'Inactive' }) {
  return <span className="rounded border border-slate-500/40 bg-slate-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-slate-300">{label}</span>;
}
const sigHex = (s) => s === 'Bullish' ? '#34d399' : s === 'Bearish' ? '#f87171' : '#94a3b8';
function Spark({ data, color = '#94a3b8', width = 72, height = 22 }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const rng = (max - min) || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * (width - 2) + 1;
    const y = height - 1 - ((v - min) / rng) * (height - 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const last = data[data.length - 1];
  const lx = width - 1;
  const ly = height - 1 - ((last - min) / rng) * (height - 2);
  return (
    <svg width={width} height={height} className="shrink-0" aria-hidden="true">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lx.toFixed(1)} cy={ly.toFixed(1)} r="1.6" fill={color} />
    </svg>
  );
}
const sigColor = (s) => s === 'Bullish' ? 'text-emerald-400' : s === 'Bearish' ? 'text-red-400' : 'text-slate-400';
const riskStateColor = (s) => ({ Low: 'text-emerald-400', Normal: 'text-lime-400', Deep: 'text-emerald-400',
  Elevated: 'text-amber-400', High: 'text-orange-400', Thin: 'text-orange-400', Extreme: 'text-red-400' }[s] || 'text-slate-300');

function RiskSection({ d }) {
  const r = d.risk;
  if (!r) return <ComingSoonSection section={sec('risk')} />;
  const lvlColor = riskStateColor(r.level);
  return (
    <div className="space-y-5">
      <SectionHead icon={ShieldAlert} title="BTCIQ Risk" blurb={sec('risk').blurb} coin={d.symbol || 'BTC'} />
      <AiReview section="risk" text="Albert is reviewing current risk…" voice />
      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <div className="flex flex-wrap items-center gap-6">
          <div>
            <p className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-slate-400">Overall Risk Level<InfoTip below text={`How turbulent ${(d.symbol || 'BTC')} is right now on a 0–100 scale. It measures the size of the swings, not the direction — high risk can happen in both up and down markets.`} /></p>
            <p className={`text-4xl font-black ${lvlColor}`}>{r.level}</p>
            <p className="text-xs text-slate-500">score {r.score}/100 · direction-independent</p>
          </div>
          <div className="flex-1">
            <div className="flex gap-1">
              {r.state_scale.map((s) => (
                <div key={s} className={`flex-1 rounded py-1 text-center text-[10px] font-semibold ${s === r.level ? `${riskStateColor(s)} bg-slate-800 ring-1 ring-slate-600` : 'text-slate-600'}`}>{s}</div>
              ))}
            </div>
            <p className="mt-3 text-xs italic text-slate-500">{r.note}</p>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <p className="mb-3 flex items-center gap-1 text-sm font-semibold text-white">Expected Move<InfoTip below text="A statistical range of where price could sit over each window, based on recent volatility. It's a likely band, not a target — price can still break out of it." /></p>
          {['24H', '7D', '30D'].map((h) => {
            const e = r.expected_move[h];
            return (
              <div key={h} className="mb-2 flex items-center justify-between text-sm">
                <span className="text-slate-400">{h}</span>
                <span className="font-mono text-slate-200">±{e.pct}% · {fmtUsd(e.low)}–{fmtUsd(e.high)}</span>
              </div>
            );
          })}
          <p className="mt-2 text-[11px] text-slate-500">Realised vol ≈ {r.realised_vol_annual}% annualised ({r.vol_percentile}th pct)</p>
        </Card>
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <p className="mb-3 flex items-center gap-1 text-sm font-semibold text-white">Key Zones<InfoTip below text="The nearest notable price levels above and below where reactions are more likely (support/resistance) and the % distance to each from spot." /></p>
          {r.upside_zone && <div className="mb-2 rounded-lg border border-red-500/20 bg-red-500/5 p-2.5 text-sm"><p className="text-[11px] text-slate-400">{r.upside_zone.label}</p><p className="font-mono font-bold text-red-300">{fmtUsd(r.upside_zone.price)} <span className="text-[11px] font-normal text-slate-500">+{r.upside_zone.distance_pct}%</span></p></div>}
          {r.downside_zone && <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2.5 text-sm"><p className="text-[11px] text-slate-400">{r.downside_zone.label}</p><p className="font-mono font-bold text-emerald-300">{fmtUsd(r.downside_zone.price)} <span className="text-[11px] font-normal text-slate-500">-{r.downside_zone.distance_pct}%</span></p></div>}
          {!r.upside_zone && !r.downside_zone && <p className="text-sm text-slate-500">No clear zones detected right now.</p>}
        </Card>
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <p className="mb-3 flex items-center gap-1 text-sm font-semibold text-white">Environment<InfoTip below text="Background conditions that can amplify risk: how much big scheduled macro events loom, and how uncertain/stale the underlying data feeds are." /></p>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-slate-400">Macro-event risk</span><span className={riskStateColor(r.macro_event_risk)}>{r.macro_event_risk}</span></div>
            <div className="flex justify-between"><span className="text-slate-400">Data uncertainty</span><span className={riskStateColor(r.data_uncertainty)}>{r.data_uncertainty}</span></div>
          </div>
          <p className="mt-2 text-[11px] text-slate-500">{r.macro_note}</p>
        </Card>
      </div>

      <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
        <div className="mb-3 flex items-center gap-2"><h3 className="flex items-center gap-1 text-sm font-semibold text-white">Risk Drivers<InfoTip below text="The individual factors feeding the risk score (volatility, leverage, liquidity, macro). Each shows its current state; items tagged Inactive are placeholders until a paid feed is added." /></h3><span className="text-[11px] text-slate-500">real + inactive</span></div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {r.drivers.map((dr, i) => (
            <div key={i} className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 p-2.5 text-sm">
              <span className="flex-1 text-slate-300">{dr.name}</span>
              {dr.demo && <DemoBadge />}
              <span className={`font-semibold ${riskStateColor(dr.state)}`}>{dr.state}</span>
              <span className="w-40 truncate text-right text-[11px] text-slate-500">{dr.value}</span>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[11px] text-slate-600">Metrics tagged Inactive (implied volatility, leverage/funding, liquidation clusters, order-book depth) are placeholders until a paid derivatives/order-book feed is connected. All other metrics are computed from real market data.</p>
      </Card>
    </div>
  );
}

function DemoMetricsCard({ title, icon: Icon, panel, sectionId }) {
  if (!panel) return <ComingSoonSection section={sec(sectionId)} />;
  const inactive = !!panel.demo;
  return (
    <div className="space-y-5">
      <SectionHead icon={Icon} title={title} blurb={sec(sectionId).blurb} />
      {!inactive && <AiReview section={sectionId} text={`Albert is reviewing ${title.toLowerCase()}…`} voice />}
      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Icon className="h-5 w-5 text-sky-400" />
          <h3 className="flex items-center gap-1 font-semibold text-white">{panel.headline}<InfoTip below text="A snapshot of what this data category is signalling. Each row shows a metric, its current value, and whether it reads bullish, bearish or neutral for BTC." /></h3>
          {inactive ? <DemoBadge /> : <span className="rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300">Live</span>}
          <span className="ml-auto text-[11px] text-slate-500">{panel.source}</span>
        </div>
        <div className="space-y-2">
          {panel.metrics.map((m, i) => (
            <div key={i} className={`flex items-center gap-3 rounded-lg border p-3 text-sm ${m.inactive ? 'border-slate-800/60 bg-slate-950/20 opacity-60' : 'border-slate-800 bg-slate-950/40'}`}>
              <span className="flex-1 text-slate-300">{m.name}</span>
              {m.inactive && <DemoBadge />}
              {!m.inactive && m.spark && <Spark data={m.spark} color={sigHex(m.signal)} />}
              <span className="font-mono text-slate-200">{m.value}</span>
              {!m.inactive && <span className={`w-16 text-right text-xs font-semibold ${sigColor(m.signal)}`}>{m.signal}</span>}
            </div>
          ))}
        </div>
        {inactive ? (
          <div className="mt-4 rounded-lg border border-slate-500/25 bg-slate-500/[0.06] p-3 text-[11px] text-slate-300/80">
            <span className="font-semibold">Inactive:</span> live data isn’t connected for this panel yet, so the values above are illustrative placeholders. Connect {panel.source} to activate real data.
          </div>
        ) : (
          <div className="mt-4 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.05] p-3 text-[11px] text-emerald-200/80">
            Live on-chain / derivatives data from {panel.source}. Any row marked <span className="font-semibold">Inactive</span> needs a paid feed and is not yet connected.
          </div>
        )}
      </Card>
    </div>
  );
}

/* ---------------- Phase A: Network & Sentiment / Exchange Flow / Morning Brief / Admin ---------------- */
function useFetch(url, deps = []) {
  const [d, setD] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    let alive = true; setLoading(true);
    fetch(url, { cache: 'no-store' }).then((r) => r.json())
      .then((j) => { if (alive) { setD(j); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, deps); // eslint-disable-line
  return [d, loading];
}

function MorningBriefCard() {
  const [d, loading] = useFetch('/api/v1/albert/brief');
  const obs = (d && d.observations) || [];
  return (
    <Card className="border-0 bg-gradient-to-br from-sky-950/40 to-slate-900 p-6 ring-1 ring-sky-900/50">
      <div className="mb-3 flex items-center gap-2">
        <img src="/albert.png" alt="Albert" className="h-7 w-7 rounded-full" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
        <h3 className="font-semibold text-white">Albert's Morning Brief</h3>
        <span className="rounded border border-sky-500/40 bg-sky-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-sky-300">Daily</span>
      </div>
      {loading ? <p className="text-sm text-slate-500">Albert is pulling together today's whole-market read…</p>
        : !obs.length && !(d && d.take) ? <p className="text-sm text-slate-500">Brief is generating — check back in a moment.</p>
          : (<>
            <ul className="space-y-1.5">{obs.map((o, i) => (<li key={i} className="flex gap-2 text-sm text-slate-300"><span className="text-sky-500">•</span>{o}</li>))}</ul>
            {d && d.take && <p className="mt-3 rounded-lg border border-sky-500/20 bg-sky-500/[0.06] p-3 text-sm font-medium text-white"><span className="text-sky-400">Take:</span> {d.take}</p>}
          </>)}
    </Card>
  );
}

function NetworkSentimentSection() {
  const [fg, fgLoad] = useFetch('/api/v1/fear-greed');
  const [nh, nhLoad] = useFetch('/api/v1/network-health');
  const fgColor = (v) => v == null ? '#94a3b8' : v <= 25 ? '#f87171' : v <= 45 ? '#fb923c' : v <= 55 ? '#94a3b8' : v <= 75 ? '#a3e635' : '#34d399';
  const fgHist = (fg && fg.history || []).map((h) => ({ ts: h.ts, v: h.value }));
  const hseries = (nh && nh.hashrate_series || []);
  return (
    <div className="space-y-5">
      <SectionHead icon={Activity} title="Network & Sentiment" blurb={sec('network').blurb} coin="BTC" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Fear & Greed */}
        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <div className="mb-3 flex items-center gap-2"><h3 className="flex items-center gap-1 font-semibold text-white">Fear &amp; Greed Index<InfoTip below text="A 0-100 gauge of crypto crowd emotion (0 = Extreme Fear, 100 = Extreme Greed). Extremes can mark turning points but are not timing signals." /></h3><span className="rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300">Live</span></div>
          {fgLoad ? <p className="text-sm text-slate-500">Loading sentiment…</p> : !fg || fg.value == null ? <p className="text-sm text-slate-500">No Fear &amp; Greed data available.</p> : (<>
            <div className="flex items-center gap-5">
              <div className="text-center"><LevGauge value={fg.value} label={fg.label} color={fgColor(fg.value)} /></div>
              <div className="text-sm text-slate-400">
                <div>Now: <span className="font-bold" style={{ color: fgColor(fg.value) }}>{fg.value} · {fg.label}</span></div>
                <div className="mt-1">1 week ago: <span className="text-slate-200">{fg.week_ago}</span></div>
                <div>1 month ago: <span className="text-slate-200">{fg.month_ago}</span></div>
              </div>
            </div>
            <div className="mt-3 h-20 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={fgHist} margin={{ top: 2, right: 4, left: -28, bottom: 0 }}>
                  <YAxis domain={[0, 100]} hide /><XAxis dataKey="ts" hide />
                  <ReferenceLine y={25} stroke="#7f1d1d" strokeDasharray="3 3" /><ReferenceLine y={75} stroke="#14532d" strokeDasharray="3 3" />
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }} labelFormatter={() => ''} formatter={(v) => [v, 'F&G']} />
                  <Line type="monotone" dataKey="v" stroke="#38bdf8" strokeWidth={1.6} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-[11px] text-slate-400">{fg.read}</p>
          </>)}
        </Card>
        {/* Network health */}
        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <div className="mb-3 flex items-center gap-2"><h3 className="flex items-center gap-1 font-semibold text-white">Network Health<InfoTip below text="How secure and congested the Bitcoin network is: hashrate (mining power securing it), difficulty (auto-adjusts every ~2 weeks), mempool backlog and fees to confirm quickly." /></h3><span className="rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300">Live</span></div>
          {nhLoad ? <p className="text-sm text-slate-500">Loading network data…</p> : !nh || nh.hashrate_ehs == null ? <p className="text-sm text-slate-500">No network data available.</p> : (<>
            <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
              <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[10px] text-slate-500">Hashrate</div><div className="font-semibold text-white">{nh.hashrate_ehs} EH/s</div></div>
              <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[10px] text-slate-500">Next difficulty</div><div className={`font-semibold ${(nh.difficulty_change_pct || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{(nh.difficulty_change_pct >= 0 ? '+' : '')}{nh.difficulty_change_pct}%</div><div className="text-[10px] text-slate-600">~{nh.retarget_days}d</div></div>
              <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[10px] text-slate-500">Fees ({nh.fees && nh.fees.state})</div><div className="font-semibold text-white">{nh.fees && nh.fees.fastest} sat/vB</div></div>
              <div className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[10px] text-slate-500">Mempool</div><div className="font-semibold text-white">{nh.mempool && nh.mempool.congestion}</div><div className="text-[10px] text-slate-600">{nh.mempool && Number(nh.mempool.count).toLocaleString()} txns</div></div>
            </div>
            <div className="mt-3 h-20 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={hseries} margin={{ top: 2, right: 4, left: -22, bottom: 0 }}>
                  <YAxis hide domain={['auto', 'auto']} /><XAxis dataKey="ts" hide />
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }} labelFormatter={() => ''} formatter={(v) => [v + ' EH/s', 'Hashrate']} />
                  <Line type="monotone" dataKey="v" stroke="#fbbf24" strokeWidth={1.6} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-[11px] text-slate-400">{nh.read}</p>
          </>)}
        </Card>
      </div>
    </div>
  );
}

function ExchangeNetFlowCard() {
  const [d, loading] = useFetch('/api/v1/exchange-flows');
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

// ---- Data Audit (Composite Price · Provenance · GDELT · Cross-Asset · FRED Macro) ----
function ConfTag({ level }) {
  const l = (level || 'LOW').toUpperCase();
  const cls = l === 'HIGH' ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
    : l === 'MEDIUM' ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
      : 'border-red-500/40 bg-red-500/10 text-red-300';
  return <span className={`rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${cls}`}>{l} confidence</span>;
}

function CompositePriceCard() {
  const [d, loading] = useFetch('/api/v1/composite-price');
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
  const [d, loading] = useFetch('/api/v1/cross-asset');
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
  const [d, loading] = useFetch('/api/v1/news-signals');
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
  const [d, loading] = useFetch('/api/v1/macro-fred');
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


function AdminSection() {
  const [d, loading] = useFetch('/api/v1/admin/overview');
  const stColor = (s) => s === 'Active' ? 'text-emerald-400' : 'text-slate-500';
  const ageColor = (m) => m == null ? 'text-slate-600' : m < 60 ? 'text-emerald-400' : m < 360 ? 'text-amber-400' : 'text-red-400';
  const em = (d && d.costs && d.costs.emergent) || {};
  return (
    <div className="space-y-5">
      <SectionHead icon={ShieldCheck} title="Admin" blurb={sec('admin').blurb} coin="BTC" />
      {loading ? <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800"><p className="text-sm text-slate-500">Loading admin overview…</p></Card> : !d || d.status !== 'ready' ? <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800"><p className="text-sm text-slate-500">Admin data unavailable.</p></Card> : (<>
        {/* KPIs */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-slate-800 bg-slate-900 p-4"><div className="text-[11px] text-slate-500">Integrations active</div><div className="text-2xl font-bold text-white">{d.integrations_active}<span className="text-sm text-slate-500">/{d.integrations_total}</span></div></div>
          <div className="rounded-lg border border-slate-800 bg-slate-900 p-4"><div className="text-[11px] text-slate-500">LLM calls (total)</div><div className="text-2xl font-bold text-white">{d.usage.llm_calls_total}</div><div className="text-[10px] text-slate-600">{d.usage.llm_calls_today} today</div></div>
          <div className="rounded-lg border border-slate-800 bg-slate-900 p-4"><div className="text-[11px] text-slate-500">Est. LLM cost</div><div className="text-2xl font-bold text-white">${d.costs.est_llm_cost_usd}</div><div className="text-[10px] text-slate-600">${d.costs.est_llm_cost_today_usd} today</div></div>
          <div className="rounded-lg border border-slate-800 bg-slate-900 p-4"><div className="text-[11px] text-slate-500">Whales tracked</div><div className="text-2xl font-bold text-white">{d.usage.whales_tracked}</div></div>
        </div>

        {/* Integrations */}
        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <h3 className="mb-3 font-semibold text-white">Integrations</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-wider text-slate-500"><th className="pb-2">Service</th><th className="pb-2">Category</th><th className="pb-2">Auth</th><th className="pb-2">Cost</th><th className="pb-2 text-right">Status</th></tr></thead>
              <tbody>{(d.integrations || []).map((it, i) => (
                <tr key={i} className="border-t border-slate-800/60"><td className="py-2 font-medium text-slate-200">{it.name}</td><td className="py-2 text-slate-400">{it.category}</td><td className="py-2 text-slate-500">{it.auth}</td><td className="py-2 text-slate-500">{it.cost}</td><td className={`py-2 text-right font-semibold ${stColor(it.status)}`}>{it.status === 'Active' ? '● Active' : '○ ' + it.status}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </Card>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Emergent cost */}
          <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
            <h3 className="mb-3 flex items-center gap-1 font-semibold text-white">Emergent LLM Cost<InfoTip below text="Cost of the Gemini model calls made via your Emergent Universal LLM key. Figures are a rough estimate from call counts — exact spend is in your Emergent dashboard." /></h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded border border-slate-800 bg-slate-950/40 p-3"><div className="text-[11px] text-slate-500">Model</div><div className="font-mono text-slate-200">{em.model}</div></div>
              <div className="rounded border border-slate-800 bg-slate-950/40 p-3"><div className="text-[11px] text-slate-500">Status</div><div className={`font-semibold ${stColor(em.status)}`}>{em.status}</div></div>
              <div className="rounded border border-slate-800 bg-slate-950/40 p-3"><div className="text-[11px] text-slate-500">Calls (total / today)</div><div className="font-semibold text-white">{em.llm_calls_total} / {em.llm_calls_today}</div></div>
              <div className="rounded border border-slate-800 bg-slate-950/40 p-3"><div className="text-[11px] text-slate-500">Est. cost (total / today)</div><div className="font-semibold text-white">${em.est_cost_total_usd} / ${em.est_cost_today_usd}</div></div>
            </div>
            <p className="mt-3 text-[11px] italic text-slate-500">{em.billing_note}</p>
          </Card>

          {/* Data freshness */}
          <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
            <h3 className="mb-3 font-semibold text-white">Data freshness</h3>
            <div className="space-y-1.5">{(d.freshness || []).map((f, i) => (
              <div key={i} className="flex items-center justify-between text-sm"><span className="text-slate-300">{f.source}</span><span className={`font-mono ${ageColor(f.age_min)}`}>{f.age_min == null ? 'no data' : f.age_min < 60 ? `${f.age_min}m ago` : `${(f.age_min / 60).toFixed(1)}h ago`}</span></div>
            ))}</div>
          </Card>
        </div>

        {/* Usage + scheduler + collections */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
            <h3 className="mb-3 font-semibold text-white">Usage & content</h3>
            <div className="grid grid-cols-2 gap-2 text-sm">
              {[['Cached Albert insights', d.usage.cached_insights], ['Smart alerts', d.usage.alerts_total], ['Forecast runs logged', d.usage.runs_logged], ['Whales tracked', d.usage.whales_tracked]].map(([k, v], i) => (
                <div key={i} className="rounded border border-slate-800 bg-slate-950/40 p-2.5"><div className="text-[11px] text-slate-500">{k}</div><div className="font-semibold text-white">{v}</div></div>
              ))}
            </div>
            <h4 className="mb-2 mt-4 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Scheduler jobs</h4>
            {(d.scheduler_jobs || []).length ? <div className="space-y-1 text-[11px]">{d.scheduler_jobs.map((j, i) => (<div key={i} className="flex justify-between"><span className="font-mono text-slate-300">{j.id}</span><span className="text-slate-500">{j.next_run ? new Date(j.next_run).toLocaleString() : '—'}</span></div>))}</div> : <p className="text-[11px] text-slate-500">No scheduled jobs reported.</p>}
          </Card>

          <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
            <h3 className="mb-3 font-semibold text-white">Database collections</h3>
            <div className="grid grid-cols-2 gap-1.5 text-sm">{Object.entries(d.collections || {}).map(([k, v], i) => (
              <div key={i} className="flex justify-between rounded border border-slate-800/60 bg-slate-950/40 px-2.5 py-1.5"><span className="font-mono text-[11px] text-slate-400">{k}</span><span className="font-semibold text-slate-200">{v}</span></div>
            ))}</div>
          </Card>
        </div>
        <p className="text-[11px] text-slate-600">As of {d.as_of ? new Date(d.as_of).toLocaleString() : '—'}. Costs for free/keyless feeds are $0; the only metered cost is the Emergent LLM key.</p>
      </>)}
    </div>
  );
}

/* ---------------- Leverage screen ---------------- */
function LevGauge({ value = 0, label = '', color = '#f87171' }) {
  const v = Math.max(0, Math.min(100, value || 0));
  const R = 34, C = Math.PI * R; // semicircle
  const off = C * (1 - v / 100);
  return (
    <div className="flex flex-col items-center">
      <svg width="96" height="58" viewBox="0 0 96 58">
        <path d="M8 52 A40 40 0 0 1 88 52" fill="none" stroke="#1e293b" strokeWidth="8" strokeLinecap="round" />
        <path d="M8 52 A40 40 0 0 1 88 52" fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={C} strokeDashoffset={off} />
        <text x="48" y="46" textAnchor="middle" className="fill-white" style={{ fontSize: 18, fontWeight: 700 }}>{Math.round(v)}</text>
      </svg>
      <span className="text-[11px] font-semibold" style={{ color }}>{label}</span>
    </div>
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
    fetch(`/api/v1/leverage?timeframe=${tf}`, { cache: 'no-store' })
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

      <Card className="border-0 bg-slate-900 p-4 ring-1 ring-slate-800">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div><div className="text-[11px] text-slate-500">BTC price</div><div className="text-lg font-bold text-white">{d.price ? '$' + Number(d.price).toLocaleString() : '—'} <span className={`text-xs font-semibold ${(d.price_change_24h || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{(d.price_change_24h >= 0 ? '+' : '')}{d.price_change_24h}%</span></div></div>
          <div><div className="text-[11px] text-slate-500">Updated</div><div className="text-sm text-slate-300">{ttime(d.as_of)}</div></div>
          <div className="ml-auto flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-950/40 p-1">
            {['1H', '4H', '1D', '7D'].map((x) => (<button key={x} onClick={() => setTf(x)} className={`rounded px-2.5 py-1 text-xs font-semibold ${tf === x ? 'bg-sky-500/20 text-sky-300 ring-1 ring-sky-500/40' : 'text-slate-500 hover:text-slate-300'}`}>{x}</button>))}
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
const fMln = (v) => (v == null ? '—' : (v >= 0 ? '+$' : '-$') + Math.abs(Number(v)).toLocaleString(undefined, { maximumFractionDigits: 0 }) + 'M');
const shortDate = (iso) => { try { return new Date(iso + (iso.length <= 10 ? 'T00:00:00Z' : '')).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' }); } catch { return iso; } };

function EtfFlowsCard() {
  const [d, setD] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    let alive = true;
    fetch('/api/v1/etf-flows', { cache: 'no-store' })
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
    fetch('/api/v1/whales/impact', { cache: 'no-store' })
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
    fetch(`/api/v1/whales/transactions?min_btc=${minBtc}&limit=40`, { cache: 'no-store' })
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
    fetch(`/api/v1/whales/history?address=${address}`, { cache: 'no-store' })
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
    fetch('/api/v1/whales', { cache: 'no-store' })
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
      fetch(`/api/v1/whale-activity?address=${addr}&limit=10`, { cache: 'no-store' })
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

function SettingsSection({ onManualRun }) {
  const symbol = React.useContext(SymbolContext);
  const [pass, setPass] = React.useState('');
  const [saved, setSaved] = React.useState(false);
  React.useEffect(() => {
    if (typeof window !== 'undefined') setPass(window.localStorage.getItem('btciq_admin_passcode') || '');
  }, []);
  const save = () => { if (typeof window !== 'undefined') { window.localStorage.setItem('btciq_admin_passcode', pass); setSaved(true); setTimeout(() => setSaved(false), 2000); } };
  const sources = [
    ['Market data (BTC OHLCV, live price)', 'ccxt · Kraken/Coinbase', 'Live'],
    ['Dominance / market cap', 'CoinGecko', 'Live'],
    ['Cross-market (equities, DXY, gold)', 'Yahoo Finance / Stooq', 'Live'],
    ['News', 'RSS (CoinDesk, Cointelegraph, Fed…)', 'Live'],
    ['On-chain / Smart Money', 'BGeometrics · blockchain.com · Glassnode', 'Live'],
    ['Whale wallets (balances)', 'mempool.space · blockchain.com', 'Live'],
    ['Derivatives (OI, funding, long/short)', 'OKX', 'Live'],
    ['Sentiment (Fear & Greed)', 'alternative.me', 'Live'],
    ['ETF flows (US spot BTC)', 'Farside · bitbo mirror', 'Live'],
    ['Order-book / IV / liquidations', 'Deribit / CoinGlass', 'Inactive — paid feed'],
    ['Social sentiment', 'LunarCrush', 'Inactive — paid feed'],
  ];
  return (
    <div className="space-y-5">
      <SectionHead icon={Cpu} title="Settings" blurb={sec('settings').blurb} coin={symbol} />
      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <h3 className="mb-1 flex items-center gap-2 font-semibold text-white"><Lock className="h-4 w-4 text-amber-400" />Admin passcode</h3>
        <p className="mb-3 text-xs text-slate-500">Required to trigger a manual BitMarkAI forecast run. Stored only in this browser. Manual runs are rate-limited and audit-logged.</p>
        <div className="flex flex-wrap items-center gap-2">
          <input type="password" value={pass} onChange={(e) => setPass(e.target.value)} placeholder="Enter admin passcode"
            className="w-64 rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 focus:border-sky-500/50 focus:outline-none" />
          <Button onClick={save} className="bg-sky-500 hover:bg-sky-400">Save</Button>
          {saved && <span className="text-xs font-semibold text-emerald-400">Saved ✓</span>}
        </div>
      </Card>
      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <h3 className="mb-3 font-semibold text-white">Data sources</h3>
        <div className="space-y-1.5">
          {sources.map(([name, prov, status], i) => (
            <div key={i} className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-2.5 text-sm">
              <span className="flex-1 text-slate-300">{name}</span>
              <span className="text-[11px] text-slate-500">{prov}</span>
              <span className={`w-32 text-right text-xs font-semibold ${status === 'Live' ? 'text-emerald-400' : 'text-amber-300'}`}>{status}</span>
            </div>
          ))}
        </div>
      </Card>
      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <h3 className="mb-2 font-semibold text-white">About & compliance</h3>
        <p className="text-xs leading-relaxed text-slate-400">BTCIQ — Bitcoin Market Analysis, powered by BitCentAI, our Bitcoin-Centred Intelligence Engine. BitMarkAI measures the market and produces probability-based forecasts. Albert is BTCIQ’s HuCentAI Quant Analyst.</p>
        <p className="mt-3 text-[11px] leading-relaxed text-slate-500">BTCIQ provides Bitcoin market analysis, probability-based forecasts and educational information. It does not provide personalised financial advice or guarantee future outcomes. Albert is an original fictional BTCIQ HuCentAI Quant character and is not Albert Einstein.</p>
        <a href="https://btciq.app" target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-sky-400 hover:text-sky-300"><Globe className="h-3 w-3" />btciq.app</a>
      </Card>
    </div>
  );
}

function DrawableChart({ ohlc }) {
  const symbol = React.useContext(SymbolContext);
  const [tool, setTool] = React.useState('cursor');
  const [pending, setPending] = React.useState(null);
  const [hover, setHover] = React.useState(null);
  const [measure, setMeasure] = React.useState(null);
  const [fs, setFs] = React.useState(false);
  const [snapMode, setSnapMode] = React.useState('ohlc');
  const [layouts, setLayouts] = React.useState({ Default: [] });
  const [activeLayout, setActiveLayout] = React.useState('Default');
  const [livePrice, setLivePrice] = React.useState(null);
  const [toasts, setToasts] = React.useState([]);
  const svgRef = React.useRef(null);
  const LKEY = 'btciq_layouts';

  React.useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      const raw = window.localStorage.getItem(LKEY);
      if (raw) {
        const o = JSON.parse(raw);
        if (o && o.layouts && typeof o.layouts === 'object' && Object.keys(o.layouts).length) {
          setLayouts(o.layouts);
          setActiveLayout(o.active && o.layouts[o.active] ? o.active : Object.keys(o.layouts)[0]);
          return;
        }
      }
      const legacy = JSON.parse(window.localStorage.getItem('btciq_drawings'));
      if (Array.isArray(legacy)) {
        const seed = { Default: legacy };
        setLayouts(seed); setActiveLayout('Default');
        window.localStorage.setItem(LKEY, JSON.stringify({ active: 'Default', layouts: seed }));
      }
    } catch (e) { /* noop */ }
  }, []);

  React.useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setFs(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // live BTC price for Ruler Alerts
  React.useEffect(() => {
    let on = true;
    const fetchP = async () => {
      try { const r = await fetch('/api/v1/ticker'); const j = await r.json(); if (on && j && typeof j.price === 'number') setLivePrice(j.price); } catch (e) { /* noop */ }
    };
    fetchP();
    const id = setInterval(fetchP, 20000);
    return () => { on = false; clearInterval(id); };
  }, []);

  const draw = layouts[activeLayout] || [];
  const persist = (nextLayouts, nextActive) => {
    const active = nextActive !== undefined ? nextActive : activeLayout;
    setLayouts(nextLayouts);
    if (nextActive !== undefined) setActiveLayout(nextActive);
    if (typeof window !== 'undefined') window.localStorage.setItem(LKEY, JSON.stringify({ active, layouts: nextLayouts }));
  };
  const save = (next) => persist({ ...layouts, [activeLayout]: next });

  const switchLayout = (nm) => { if (layouts[nm]) { persist(layouts, nm); setTool('cursor'); setPending(null); setMeasure(null); } };
  const newLayout = () => {
    const nm = (window.prompt('Name this new layout:') || '').trim().slice(0, 24);
    if (!nm) return;
    if (layouts[nm]) { window.alert('A layout with that name already exists.'); return; }
    persist({ ...layouts, [nm]: [] }, nm); setTool('cursor');
  };
  const renameLayout = () => {
    const nm = (window.prompt('Rename layout to:', activeLayout) || '').trim().slice(0, 24);
    if (!nm || nm === activeLayout) return;
    if (layouts[nm]) { window.alert('That name already exists.'); return; }
    const nl = {}; Object.keys(layouts).forEach((k) => { nl[k === activeLayout ? nm : k] = layouts[k]; });
    persist(nl, nm);
  };
  const delLayout = () => {
    if (Object.keys(layouts).length <= 1) { save([]); return; }
    if (!window.confirm(`Delete layout "${activeLayout}" and everything on it?`)) return;
    const nl = { ...layouts }; delete nl[activeLayout];
    persist(nl, Object.keys(nl)[0]);
  };

  const data = ohlc || [];
  const W = 1000, H = 440, pL = 58, pR = 54, pT = 14, pB = 30;
  const plotW = W - pL - pR, plotH = H - pT - pB;
  const n = data.length;
  if (n < 2) return <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800"><p className="text-sm text-slate-500">Chart data loading…</p></Card>;
  const vals = data.flatMap((c) => [c.h, c.l]);
  const mn = Math.min(...vals), mx = Math.max(...vals), pad = (mx - mn) * 0.06 || 1;
  const lo = mn - pad, hi = mx + pad;
  const cw = Math.max(2, (plotW / n) * 0.62);
  const xAt = (i) => pL + (i / (n - 1)) * plotW;
  const yAt = (p) => pT + (1 - (p - lo) / (hi - lo)) * plotH;
  const idxOf = (t) => data.findIndex((c) => c.t === t);
  const fUsd = (v) => '$' + Math.round(v).toLocaleString();
  const FIBS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
  const SNAP_PX = 12;

  const beep = (up) => {
    try {
      const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
      const ctx = new AC(); const o = ctx.createOscillator(); const g = ctx.createGain();
      o.connect(g); g.connect(ctx.destination); o.type = 'sine'; o.frequency.value = up ? 880 : 440; g.gain.value = 0.06;
      o.start(); setTimeout(() => { o.stop(); ctx.close(); }, 220);
    } catch (e) { /* noop */ }
  };
  const fireAlert = (dr, side) => {
    const msg = `${symbol} ${side === 'above' ? 'crossed above' : 'dropped below'} ${fUsd(dr.price)}`;
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, up: side === 'above' }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 8000);
    try { if ('Notification' in window && Notification.permission === 'granted') new Notification('BTCIQ Price Alert', { body: msg }); } catch (e) { /* noop */ }
    beep(side === 'above');
  };

  // check ruler alerts whenever the live price updates
  React.useEffect(() => {
    if (livePrice == null) return;
    const cur = layouts[activeLayout] || [];
    let changed = false;
    const next = cur.map((dr) => {
      if (dr.type !== 'alert' || dr.triggered) return dr;
      const side = livePrice >= dr.price ? 'above' : 'below';
      if (dr.side == null) { changed = true; return { ...dr, side }; }
      const touched = Math.abs(livePrice - dr.price) / dr.price <= 0.0005;
      if (side !== dr.side || touched) { changed = true; fireAlert(dr, side); return { ...dr, triggered: true, side }; }
      return dr;
    });
    if (changed) save(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [livePrice]);

  const snapAt = (i, rawY) => {
    const c = data[i]; if (!c) return null;
    let cand;
    if (snapMode === 'close') cand = [['C', c.c]];
    else if (snapMode === 'hl') cand = [['H', c.h], ['L', c.l]];
    else cand = [['O', c.o], ['H', c.h], ['L', c.l], ['C', c.c]];
    let best = null, bd = 1e9;
    cand.forEach(([label, val]) => { const d = Math.abs(yAt(val) - rawY); if (d < bd) { bd = d; best = { label, val }; } });
    return best && bd <= SNAP_PX ? best : null;
  };

  const toLocal = (e) => {
    const svg = svgRef.current; const pt = svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const l = pt.matrixTransform(svg.getScreenCTM().inverse());
    let i = Math.round((l.x - pL) / plotW * (n - 1)); i = Math.max(0, Math.min(n - 1, i));
    let price = lo + (1 - (l.y - pT) / plotH) * (hi - lo);
    let snapLabel = null;
    if (snapMode !== 'off' && tool !== 'cursor') {
      const s = snapAt(i, l.y);
      if (s) { price = s.val; snapLabel = s.label; }
    }
    price = Math.round(price);
    return { i, t: data[i].t, price, x: xAt(i), y: snapLabel ? yAt(price) : l.y, snap: snapLabel };
  };
  const TWO_PT = ['trend', 'fib', 'measure'];
  const onClick = (e) => {
    if (tool === 'cursor') return;
    const p = toLocal(e);
    if (tool === 'hline') { save([...draw, { type: 'hline', price: p.price }]); }
    else if (tool === 'alert') {
      try { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission(); } catch (er) { /* noop */ }
      const side = livePrice != null ? (livePrice >= p.price ? 'above' : 'below') : null;
      save([...draw, { type: 'alert', price: p.price, side, triggered: false }]);
    }
    else if (tool === 'note') { const text = window.prompt('Note text:'); if (text) save([...draw, { type: 'note', t: p.t, price: p.price, text: text.slice(0, 60) }]); }
    else if (TWO_PT.includes(tool)) {
      if (!pending || pending.tool !== tool) { setPending({ tool, t: p.t, price: p.price }); if (tool === 'measure') setMeasure(null); }
      else {
        const a = { t: pending.t, price: pending.price }, b = { t: p.t, price: p.price };
        if (tool === 'trend') save([...draw, { type: 'trend', a, b }]);
        else if (tool === 'fib') save([...draw, { type: 'fib', a, b }]);
        else if (tool === 'measure') setMeasure({ a, b });
        setPending(null);
      }
    } else if (tool === 'erase') {
      const px = xAt(p.i), py = yAt(p.price);
      let best = -1, bd = 1e9;
      draw.forEach((dr, k) => {
        let dist = 1e9;
        if (dr.type === 'hline' || dr.type === 'alert') dist = Math.abs(yAt(dr.price) - py);
        else if (dr.type === 'note') dist = Math.hypot(xAt(Math.max(0, idxOf(dr.t))) - px, yAt(dr.price) - py);
        else if (dr.type === 'trend' || dr.type === 'fib') { const ax = xAt(Math.max(0, idxOf(dr.a.t))), ay = yAt(dr.a.price), bx = xAt(Math.max(0, idxOf(dr.b.t))), by = yAt(dr.b.price); dist = Math.min(Math.hypot(ax - px, ay - py), Math.hypot(bx - px, by - py)); }
        if (dist < bd) { bd = dist; best = k; }
      });
      if (best >= 0 && bd < 40) save(draw.filter((_, k) => k !== best));
    }
  };
  const renderFib = (a, b, k, ghost) => {
    const ai = idxOf(a.t), bi = ghost ? b.i : idxOf(b.t);
    if (ai < 0 || (!ghost && bi < 0)) return null;
    const x0 = Math.min(xAt(ai), xAt(bi < 0 ? ai : bi));
    return (
      <g key={k} opacity={ghost ? 0.6 : 1}>
        {FIBS.map((L, j) => {
          const price = b.price + (a.price - b.price) * L;
          const y = yAt(price);
          return (<g key={j}><line x1={x0} y1={y} x2={W - pR} y2={y} stroke="#f59e0b" strokeWidth={L === 0 || L === 1 ? 1.5 : 1} strokeOpacity={0.75} strokeDasharray={L === 0 || L === 1 ? '' : '4 4'} /><text x={x0 + 3} y={y - 3} fontSize="10" fill="#fbbf24">{(L * 100).toFixed(1)}% · {fUsd(price)}</text></g>);
        })}
      </g>
    );
  };
  const TOOLS = [['cursor', 'Cursor'], ['trend', 'Trendline'], ['hline', 'Horizontal'], ['alert', 'Alert'], ['fib', 'Fib'], ['measure', 'Measure'], ['note', 'Note'], ['erase', 'Erase']];
  const hint = { trend: pending?.tool === 'trend' ? 'Click a second point to finish the trendline.' : 'Click two points to draw a trendline.',
    fib: pending?.tool === 'fib' ? 'Click the second swing point to place Fibonacci levels.' : 'Click a swing high then a swing low (or vice-versa) for Fibonacci.',
    measure: pending?.tool === 'measure' ? 'Click the end point to measure the move.' : 'Click start then end to measure price & % move.',
    hline: 'Click at a price to drop a horizontal level.', note: 'Click to place a note, then type its text.',
    alert: `Click at a price to arm a ruler alert — it pings (sound + banner) when ${symbol} touches it.`,
    erase: 'Click near a drawing to remove it.', cursor: 'Pick a tool to annotate. ' }[tool];
  const alertCount = draw.filter((dr) => dr.type === 'alert' && !dr.triggered).length;

  let measureView = null;
  if (measure) {
    const ai = idxOf(measure.a.t), bi = idxOf(measure.b.t);
    if (ai >= 0 && bi >= 0) {
      const up = measure.b.price >= measure.a.price;
      const col = up ? '#34d399' : '#f87171';
      const pct = ((measure.b.price - measure.a.price) / measure.a.price * 100).toFixed(2);
      const dol = measure.b.price - measure.a.price;
      const x1 = xAt(ai), x2 = xAt(bi), y1 = yAt(measure.a.price), y2 = yAt(measure.b.price);
      measureView = (<g><rect x={Math.min(x1, x2)} y={Math.min(y1, y2)} width={Math.abs(x2 - x1) || 1} height={Math.abs(y2 - y1) || 1} fill={col} fillOpacity={0.12} stroke={col} strokeOpacity={0.5} /><rect x={(x1 + x2) / 2 - 66} y={(y1 + y2) / 2 - 14} width="132" height="28" rx="5" fill="#0f172a" stroke={col} /><text x={(x1 + x2) / 2} y={(y1 + y2) / 2 + 4} textAnchor="middle" fontSize="11" fill={col}>{up ? '+' : ''}{fUsd(dol)} · {up ? '+' : ''}{pct}% · {Math.abs(bi - ai)} bars</text></g>);
    }
  }

  return (
    <Card className={`relative flex flex-col border-0 bg-slate-900 p-4 ring-1 ring-slate-800 ${fs ? 'fixed inset-0 z-[100] overflow-auto rounded-none' : ''}`}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <CandlestickChart className="h-4 w-4 text-amber-400" />
        <h3 className="text-sm font-semibold text-white">Draw Board · {symbol} {data.length}-day</h3>
        <div className="flex items-center gap-1 rounded-md bg-slate-800 px-1.5 py-0.5">
          <Layers className="h-3.5 w-3.5 text-slate-400" />
          <select value={activeLayout} onChange={(e) => switchLayout(e.target.value)} className="max-w-[120px] bg-transparent text-xs font-medium text-slate-200 focus:outline-none" title="Switch drawing layout">
            {Object.keys(layouts).map((nm) => <option key={nm} value={nm} className="bg-slate-900">{nm}</option>)}
          </select>
          <button onClick={newLayout} title="New layout" className="px-1 text-sm font-bold text-slate-400 hover:text-emerald-300">+</button>
          <button onClick={renameLayout} title="Rename layout" className="px-0.5 text-[10px] text-slate-400 hover:text-sky-300">Ren</button>
          <button onClick={delLayout} title="Delete layout" className="px-1 text-xs text-slate-400 hover:text-red-300">✕</button>
        </div>
        {livePrice != null && <span className="flex items-center gap-1 text-[11px] text-slate-400"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />Live {fUsd(livePrice)}</span>}
        {alertCount > 0 && <span className="flex items-center gap-1 rounded-md bg-rose-500/15 px-2 py-0.5 text-[11px] font-medium text-rose-200 ring-1 ring-rose-500/30"><Bell className="h-3 w-3" />{alertCount} armed</span>}
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-1">
        {TOOLS.map(([id, l]) => (
          <button key={id} onClick={() => { setTool(id); setPending(null); }} className={`rounded-md px-2.5 py-1 text-xs font-medium ${tool === id ? 'bg-sky-500/20 text-sky-200 ring-1 ring-sky-500/40' : 'bg-slate-800 text-slate-400 hover:text-slate-200'}`}>{l}</button>
        ))}
        <button onClick={() => { save([]); setMeasure(null); }} className="rounded-md bg-red-500/10 px-2.5 py-1 text-xs font-medium text-red-300 hover:bg-red-500/20">Clear all</button>
        <div className="flex items-center gap-1 rounded-md bg-slate-800 px-1.5 py-0.5">
          <Magnet className={`h-3.5 w-3.5 ${snapMode !== 'off' ? 'text-emerald-300' : 'text-slate-500'}`} />
          <select value={snapMode} onChange={(e) => setSnapMode(e.target.value)} className="bg-transparent text-xs font-medium text-slate-200 focus:outline-none" title="Snap drawing points to candles">
            <option value="off" className="bg-slate-900">Snap: Off</option>
            <option value="ohlc" className="bg-slate-900">Snap: O/H/L/C</option>
            <option value="close" className="bg-slate-900">Snap: Close</option>
            <option value="hl" className="bg-slate-900">Snap: High/Low</option>
          </select>
        </div>
        <button onClick={() => setFs(!fs)} className="ml-auto flex items-center gap-1 rounded-md border border-slate-700 px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-slate-800">{fs ? <><Minimize2 className="h-3.5 w-3.5" />Exit</> : <><Maximize2 className="h-3.5 w-3.5" />Full</>}</button>
      </div>
      {toasts.length > 0 && (<div className="pointer-events-none absolute right-4 top-24 z-[120] space-y-2">
        {toasts.map((t) => (<div key={t.id} className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold shadow-lg ring-1 ${t.up ? 'bg-emerald-500/15 text-emerald-200 ring-emerald-500/40' : 'bg-rose-500/15 text-rose-200 ring-rose-500/40'}`}><Bell className="h-3.5 w-3.5" />{t.msg}</div>))}
      </div>)}
      <div className="w-full overflow-hidden rounded-lg border border-slate-800 bg-slate-950/40">
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className={`w-full ${tool === 'cursor' ? 'cursor-default' : 'cursor-crosshair'}`} style={{ height: 'auto' }}
          onClick={onClick} onMouseMove={(e) => setHover(toLocal(e))} onMouseLeave={() => setHover(null)}>
          {[0, 0.25, 0.5, 0.75, 1].map((f, k) => { const p = hi - f * (hi - lo); return (<g key={k}><line x1={pL} y1={yAt(p)} x2={W - pR} y2={yAt(p)} stroke="#1e293b" /><text x={pL - 6} y={yAt(p) + 3} textAnchor="end" fontSize="11" fill="#64748b">${(p / 1000).toFixed(1)}k</text></g>); })}
          {/* candlesticks */}
          {data.map((c, i) => { const up = c.c >= c.o; const col = up ? '#34d399' : '#f87171'; const cx = xAt(i); const top = yAt(Math.max(c.o, c.c)); const bot = yAt(Math.min(c.o, c.c)); return (<g key={i}><line x1={cx} y1={yAt(c.h)} x2={cx} y2={yAt(c.l)} stroke={col} strokeWidth="1" /><rect x={cx - cw / 2} y={top} width={cw} height={Math.max(1, bot - top)} fill={col} /></g>); })}
          {data.filter((_, i) => i % Math.ceil(n / 8) === 0).map((c, k) => { const i = data.indexOf(c); return <text key={k} x={xAt(i)} y={H - 10} textAnchor="middle" fontSize="10" fill="#64748b">{c.t}</text>; })}
          {/* live price line */}
          {livePrice != null && livePrice >= lo && livePrice <= hi && (<g pointerEvents="none"><line x1={pL} y1={yAt(livePrice)} x2={W - pR} y2={yAt(livePrice)} stroke="#38bdf8" strokeWidth="1" strokeOpacity="0.6" strokeDasharray="1 3" /><rect x={W - pR} y={yAt(livePrice) - 8} width={pR} height="16" fill="#0ea5e9" /><text x={W - pR + 4} y={yAt(livePrice) + 4} fontSize="10" fill="#e0f2fe">{fUsd(livePrice)}</text></g>)}
          {/* saved drawings */}
          {draw.map((dr, k) => {
            if (dr.type === 'hline') return (<g key={k}><line x1={pL} y1={yAt(dr.price)} x2={W - pR} y2={yAt(dr.price)} stroke="#fbbf24" strokeWidth="1.5" strokeDasharray="6 4" /><text x={W - pR - 2} y={yAt(dr.price) - 4} textAnchor="end" fontSize="11" fill="#fbbf24">{fUsd(dr.price)}</text></g>);
            if (dr.type === 'alert') { const y = yAt(dr.price); const col = dr.triggered ? '#f43f5e' : '#fb7185'; return (<g key={k}><line x1={pL} y1={y} x2={W - pR} y2={y} stroke={col} strokeWidth="1.5" strokeDasharray="2 4" /><rect x={pL + 2} y={y - 9} width={dr.triggered ? 128 : 104} height="16" rx="3" fill="#1e293b" stroke={col} strokeWidth="0.75" /><circle cx={pL + 11} cy={y} r="2.6" fill={col} /><text x={pL + 18} y={y + 3} fontSize="10" fill={col}>{dr.triggered ? 'Triggered · ' : 'Alert · '}{fUsd(dr.price)}</text></g>); }
            if (dr.type === 'trend') { const ai = idxOf(dr.a.t), bi = idxOf(dr.b.t); if (ai < 0 || bi < 0) return null; return <line key={k} x1={xAt(ai)} y1={yAt(dr.a.price)} x2={xAt(bi)} y2={yAt(dr.b.price)} stroke="#38bdf8" strokeWidth="2" />; }
            if (dr.type === 'fib') return renderFib(dr.a, dr.b, k, false);
            if (dr.type === 'note') { const i = idxOf(dr.t); if (i < 0) return null; return (<g key={k}><circle cx={xAt(i)} cy={yAt(dr.price)} r="4" fill="#a78bfa" /><text x={xAt(i) + 7} y={yAt(dr.price) + 3} fontSize="11" fill="#c4b5fd">{dr.text}</text></g>); }
            return null;
          })}
          {measureView}
          {/* pending 2-point preview */}
          {pending && hover && (<>
            <circle cx={xAt(idxOf(pending.t))} cy={yAt(pending.price)} r="4" fill="#38bdf8" />
            {pending.tool === 'fib' ? renderFib({ t: pending.t, price: pending.price }, hover, 'ghost', true)
              : <line x1={xAt(idxOf(pending.t))} y1={yAt(pending.price)} x2={hover.x} y2={yAt(hover.price)} stroke={pending.tool === 'measure' ? '#fbbf24' : '#38bdf8'} strokeWidth="1.5" strokeDasharray="4 4" />}
          </>)}
          {/* crosshair */}
          {hover && (<g pointerEvents="none">
            <line x1={hover.x} y1={pT} x2={hover.x} y2={pT + plotH} stroke="#475569" strokeDasharray="3 3" />
            <line x1={pL} y1={hover.y} x2={W - pR} y2={hover.y} stroke="#475569" strokeDasharray="3 3" />
            <rect x={W - pR} y={hover.y - 9} width={pR} height="18" fill="#1e293b" /><text x={W - pR + 4} y={hover.y + 4} fontSize="10" fill="#e2e8f0">{fUsd(hover.price)}</text>
            <rect x={hover.x - 22} y={pT + plotH} width="44" height="16" fill="#1e293b" /><text x={hover.x} y={pT + plotH + 12} textAnchor="middle" fontSize="10" fill="#e2e8f0">{hover.t}</text>
            {hover.snap && (<g><circle cx={hover.x} cy={hover.y} r="6" fill="none" stroke="#34d399" strokeWidth="1.8" /><circle cx={hover.x} cy={hover.y} r="2.5" fill="#34d399" /><rect x={hover.x + 8} y={hover.y - 9} width="20" height="16" rx="3" fill="#064e3b" stroke="#34d399" strokeWidth="0.75" /><text x={hover.x + 18} y={hover.y + 3} textAnchor="middle" fontSize="10" fill="#6ee7b7">{hover.snap}</text></g>)}
          </g>)}
        </svg>
      </div>
      <p className="mt-2 text-[11px] text-slate-600">{hint} {snapMode !== 'off' ? `Snap "${{ ohlc: 'O/H/L/C', close: 'Close', hl: 'High/Low' }[snapMode]}" locks points to candles (green ring).` : 'Snap is off — points follow the cursor freely.'} Layout "{activeLayout}" ({draw.length} items) auto-saves to this browser. Alerts ping while this page is open.</p>
    </Card>
  );
}

function MarketIntelligenceSection({ d }) {
  const isBtc = React.useContext(SymbolContext) === 'BTC';
  return (
    <div className="space-y-8">
      <div>
        <SectionHead icon={CandlestickChart} title="Draw & Annotate" blurb="Your own lightweight chart with trendlines, horizontal levels and notes — everything you draw is saved in this browser and reloads automatically. No account needed." coin={d.symbol || 'BTC'} />
        <DrawableChart ohlc={d.chart?.ohlc} />
      </div>
      <ChartSection d={d} />
      {isBtc && <CycleSection d={d} />}
      <AnalysisSection d={d} />
    </div>
  );
}

function PerformanceHubSection({ d }) {
  const isBtc = React.useContext(SymbolContext) === 'BTC';
  return (
    <div className="space-y-8">
      {isBtc && <ScorecardSection d={d} />}
      <PerformanceSection d={d} />
      {isBtc && <DataTrustSection d={d} />}
    </div>
  );
}

function ForecastsHubSection({ d }) {
  const isBtc = React.useContext(SymbolContext) === 'BTC';
  return (
    <div className="space-y-8">
      {isBtc && <BitMarkSection d={d} />}
      <ForecastsSection d={d} />
    </div>
  );
}


/* ----------------------------- page ---------------------------------- */
// Module-level caches survive a Fast-Refresh / remount so the dashboard never
// flickers back to the full-screen loader once data has been fetched once.
let __dashCache = null;
let __tickerCache = null;
let __newsCache = null;
let __alertsCache = null;
const COMPARE_NAMES = { BTC: 'Bitcoin', ETH: 'Ethereum', SOL: 'Solana' };
const COMPARE_SYMS = ['BTC', 'ETH', 'SOL'];

function CoinSparkline({ data, up }) {
  if (!data || data.length < 2) return null;
  const w = 200, h = 44;
  const mn = Math.min(...data), mx = Math.max(...data), rng = (mx - mn) || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - mn) / rng) * (h - 4) - 2}`).join(' ');
  const col = up ? '#34d399' : '#f87171';
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-11 w-full">
      <polyline points={pts} fill="none" stroke={col} strokeWidth="1.5" />
    </svg>
  );
}

function oddsColor(v) { return v == null ? '#94a3b8' : (v >= 55 ? '#34d399' : (v <= 45 ? '#f87171' : '#fbbf24')); }

function CompareCoinCard({ d, onRemove }) {
  const up = (d.day_change_pct || 0) >= 0;
  return (
    <Card className="relative flex flex-col border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      {onRemove && <button onClick={onRemove} title="Remove coin" className="absolute right-2 top-2 rounded-full p-1 text-slate-500 hover:bg-slate-800 hover:text-red-300"><X className="h-3.5 w-3.5" /></button>}
      <div className="mb-3 flex items-center gap-2 pr-6">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-800 text-sm font-black text-sky-300">{d.symbol}</span>
        <div className="flex-1">
          <p className="text-sm font-bold text-white">{d.name}</p>
          <p className="text-[10px] uppercase tracking-wider text-slate-500">{d.symbol}/USD · {d.source}</p>
        </div>
        <div className="text-right">
          <p className="font-mono text-lg font-bold text-white">${d.price?.toLocaleString()}</p>
          <p className={`text-xs font-semibold ${up ? 'text-emerald-400' : 'text-red-400'}`}>{up ? '+' : ''}{d.day_change_pct}%</p>
        </div>
      </div>
      <CoinSparkline data={d.spark} up={up} />
      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded-lg bg-slate-950/50 p-3">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">Quant Score</p>
          <p className="text-2xl font-black" style={{ color: scoreColor(d.quant_score) }}>{d.quant_score}<span className="text-xs font-medium text-slate-500">/100</span></p>
          <p className="text-[11px]" style={{ color: scoreColor(d.quant_score) }}>{d.quant_label}</p>
        </div>
        <div className="rounded-lg bg-slate-950/50 p-3">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">Market Regime</p>
          <p className="mt-1 text-sm font-bold leading-tight text-white">{d.regime}</p>
        </div>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-center">
        <div className="rounded-lg bg-slate-950/50 p-2">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">24h higher</p>
          <p className="font-mono text-lg font-bold" style={{ color: oddsColor(d.forecast_24h?.higher) }}>{d.forecast_24h?.higher ?? '—'}%</p>
          <p className="text-[10px] text-slate-500">{d.forecast_24h?.confidence}</p>
        </div>
        <div className="rounded-lg bg-slate-950/50 p-2">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">7d higher</p>
          <p className="font-mono text-lg font-bold" style={{ color: oddsColor(d.forecast_7d?.higher) }}>{d.forecast_7d?.higher ?? '—'}%</p>
          <p className="text-[10px] text-slate-500">{d.forecast_7d?.confidence}</p>
        </div>
      </div>
      <div className="mt-2 flex justify-between rounded-lg bg-slate-950/50 p-2 text-xs">
        <span className="text-emerald-300">Support ${d.support?.toLocaleString() ?? '—'}</span>
        <span className="text-red-300">Resistance ${d.resistance?.toLocaleString() ?? '—'}</span>
      </div>
      {d.bullish?.[0] && <p className="mt-3 flex gap-1.5 text-[11px] text-slate-400"><TrendingUp className="mt-0.5 h-3 w-3 shrink-0 text-emerald-400" />{d.bullish[0]}</p>}
      {d.risk?.[0] && <p className="mt-1.5 flex gap-1.5 text-[11px] text-slate-400"><TrendingDown className="mt-0.5 h-3 w-3 shrink-0 text-red-400" />{d.risk[0]}</p>}
    </Card>
  );
}

function CompareSection() {
  const [selected, setSelected] = React.useState(['BTC', 'ETH', 'SOL']);
  const [allCoins, setAllCoins] = React.useState([]);
  const [data, setData] = React.useState({});
  const [loading, setLoading] = React.useState({ BTC: true, ETH: true, SOL: true });
  const [err, setErr] = React.useState({});

  React.useEffect(() => {
    fetch('/api/v1/compare/coins').then((r) => r.json()).then((j) => { if (j.coins) setAllCoins(j.coins); }).catch(() => {});
  }, []);

  const loadCoin = React.useCallback((s, force) => {
    setLoading((l) => ({ ...l, [s]: true }));
    setErr((e) => ({ ...e, [s]: null }));
    fetch(`/api/v1/compare/coin?symbol=${s}${force ? '&refresh=1' : ''}`)
      .then((r) => r.json())
      .then((j) => { if (j.status === 'ready') setData((d) => ({ ...d, [s]: j.data })); else setErr((e) => ({ ...e, [s]: j.reason || 'error' })); })
      .catch(() => setErr((e) => ({ ...e, [s]: 'network' })))
      .finally(() => setLoading((l) => ({ ...l, [s]: false })));
  }, []);

  React.useEffect(() => { selected.forEach((s) => { if (!data[s] && !err[s]) loadCoin(s); }); }, [selected, loadCoin, data, err]);

  const addCoin = (s) => { if (s && !selected.includes(s)) setSelected((sel) => [...sel, s]); };
  const removeCoin = (s) => setSelected((sel) => sel.length > 1 ? sel.filter((x) => x !== s) : sel);

  const nameOf = (s) => (allCoins.find((c) => c.symbol === s)?.name) || COMPARE_NAMES[s] || s;
  const pending = selected.filter((s) => loading[s] && !data[s]);
  const anyPending = pending.length > 0;
  const available = allCoins.filter((c) => !selected.includes(c.symbol));

  return (
    <div className="space-y-5">
      <SectionHead icon={Scale} title="Compare Coins" blurb={sec('compare').blurb} />

      <Card className="border-0 bg-gradient-to-br from-sky-500/10 to-violet-500/[0.06] p-4 ring-1 ring-sky-500/25">
        <div className="flex flex-wrap items-center gap-3">
          <img src="/albert.png" alt="Albert" className="h-9 w-9 rounded-full object-cover ring-2 ring-sky-500/40" />
          <div className="min-w-[220px] flex-1">
            <p className="text-sm font-semibold text-sky-100">Albert</p>
            {anyPending ? (
              <p className="flex items-center gap-2 text-xs text-slate-300"><RefreshCw className="h-3.5 w-3.5 animate-spin text-violet-300" />Crunching the quant model on {pending.map((s) => nameOf(s)).join(', ')}… first run per coin takes a few seconds, then it’s cached.</p>
            ) : (
              <p className="text-xs text-slate-300">Add any coin below to run it on the same engine. Scores are 0–100 conviction; odds are probabilities, not promises — never financial advice.</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 rounded-full border border-slate-700 bg-slate-800/60 px-2 py-1">
              <Plus className="h-3.5 w-3.5 text-sky-300" />
              <select value="" onChange={(e) => { addCoin(e.target.value); e.target.value = ''; }} disabled={!available.length} className="bg-transparent text-xs font-semibold text-slate-200 focus:outline-none disabled:opacity-50">
                <option value="" className="bg-slate-900">{available.length ? 'Add a coin…' : 'All added'}</option>
                {available.map((c) => <option key={c.symbol} value={c.symbol} className="bg-slate-900">{c.symbol} · {c.name}</option>)}
              </select>
            </div>
            <button onClick={() => selected.forEach((s) => loadCoin(s, true))} disabled={anyPending} className="flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:border-sky-500/40 hover:text-sky-300 disabled:opacity-50">
              <RefreshCw className={`h-3.5 w-3.5 ${anyPending ? 'animate-spin' : ''}`} />Recompute
            </button>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {selected.map((s) => {
          if (data[s]) return <CompareCoinCard key={s} d={data[s]} onRemove={() => removeCoin(s)} />;
          if (err[s]) return (
            <Card key={s} className="relative flex flex-col items-center justify-center border-0 bg-slate-900 p-8 text-center ring-1 ring-slate-800">
              <button onClick={() => removeCoin(s)} className="absolute right-2 top-2 rounded-full p-1 text-slate-500 hover:text-red-300"><X className="h-3.5 w-3.5" /></button>
              <p className="text-sm font-bold text-white">{nameOf(s)}</p>
              <p className="mt-1 text-xs text-red-300">Couldn’t load {s} — this market may not be available.</p>
              <button onClick={() => loadCoin(s, true)} className="mt-3 rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800">Retry</button>
            </Card>
          );
          return (
            <Card key={s} className="flex flex-col items-center justify-center border-0 bg-slate-900 p-8 text-center ring-1 ring-slate-800">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-800 text-sm font-black text-sky-300">{s}</span>
              <p className="mt-3 text-sm font-semibold text-white">{nameOf(s)}</p>
              <p className="mt-2 flex items-center gap-2 text-xs text-slate-400"><RefreshCw className="h-3.5 w-3.5 animate-spin text-violet-300" />Albert is computing…</p>
              <div className="mt-3 h-1 w-32 overflow-hidden rounded-full bg-slate-800"><div className="h-full w-1/2 animate-pulse rounded-full bg-violet-400/70" /></div>
            </Card>
          );
        })}
      </div>
      <p className="text-[11px] text-slate-600">Same price-agnostic quant engine (trend, momentum, volatility, volume) applied per coin on daily data via Kraken/Coinbase. BTC-specific context (halving cycle, dominance) isn’t shown here as it doesn’t apply to alts. Research signals only — not financial advice.</p>
    </div>
  );
}

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

const ANALOG_CAT_COLOR = {
  Macro: 'text-amber-300 bg-amber-500/15',
  'Market structure': 'text-sky-300 bg-sky-500/15',
  'On-chain': 'text-violet-300 bg-violet-500/15',
  Events: 'text-emerald-300 bg-emerald-500/15',
};

const ANALOG_OVERLAY_COLORS = ['#f7931a', '#a855f7', '#22d3ee'];

// Interpolate a rebased forward path (list of {off,v}) at a given day; null if unresolved there.
function pathValueAt(fp, day) {
  const a = (fp || []).filter((p) => p.v != null);
  if (!a.length) return null;
  if (day <= a[0].off) return a[0].v;
  if (day > a[a.length - 1].off) return null;
  for (let i = 0; i < a.length - 1; i += 1) {
    if (a[i].off <= day && day <= a[i + 1].off) {
      const t = (day - a[i].off) / ((a[i + 1].off - a[i].off) || 1);
      return a[i].v + (a[i + 1].v - a[i].v) * t;
    }
  }
  return a[a.length - 1].v;
}

// Tiny inline win/loss forward mini-chart for each Setup History row, with hover readout.
function OutcomeSpark({ points, color }) {
  const [hover, setHover] = React.useState(null);
  const pts = (points || []).filter((p) => p.v != null);
  if (pts.length < 2) return <span className="text-slate-600">—</span>;
  const w = 92; const h = 26; const pad = 2;
  const xs = pts.map((p) => p.off); const ys = pts.map((p) => p.v);
  const minX = Math.min(...xs); const maxX = Math.max(...xs);
  const minY = Math.min(...ys, 100); const maxY = Math.max(...ys, 100);
  const sx = (x) => pad + ((x - minX) / ((maxX - minX) || 1)) * (w - 2 * pad);
  const sy = (y) => h - pad - ((y - minY) / ((maxY - minY) || 1)) * (h - 2 * pad);
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${sx(p.off).toFixed(1)},${sy(p.v).toFixed(1)}`).join(' ');
  const baseY = sy(100); const end = pts[pts.length - 1];
  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left;
    let best = 0; let bd = Infinity;
    pts.forEach((p, i) => { const dd = Math.abs(sx(p.off) - px); if (dd < bd) { bd = dd; best = i; } });
    setHover(best);
  };
  const hp = hover == null ? null : pts[hover];
  const ret = hp ? Math.round((hp.v - 100) * 10) / 10 : null;
  return (
    <span className="inline-flex items-center gap-1.5" onMouseLeave={() => setHover(null)}>
      <svg width={w} height={h} className="inline-block align-middle" onMouseMove={onMove}>
        <line x1={pad} y1={baseY} x2={w - pad} y2={baseY} stroke="#334155" strokeWidth="1" strokeDasharray="2 2" />
        <path d={d} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
        {hp && <line x1={sx(hp.off)} y1={pad} x2={sx(hp.off)} y2={h - pad} stroke={color} strokeOpacity="0.45" strokeWidth="1" />}
        <circle cx={sx(end.off)} cy={sy(end.v)} r="1.8" fill={color} />
        {hp && <circle cx={sx(hp.off)} cy={sy(hp.v)} r="2.6" fill={color} stroke="#0f172a" strokeWidth="1" />}
      </svg>
      <span className="w-[68px] text-left text-[10px] font-semibold tabular-nums leading-tight">
        {hp
          ? <span>+{hp.off}d <span className={ret >= 0 ? 'text-emerald-400' : 'text-red-400'}>{ret > 0 ? '+' : ''}{ret}%</span></span>
          : <span className="text-slate-600">hover</span>}
      </span>
    </span>
  );
}

function scoreAnalog(ep, current, norm, weights) {
  let tot = 0;
  let wsum = 0;
  Object.keys(current || {}).forEach((k) => {
    const w = weights[k] == null ? 1 : weights[k];
    const a = ep.fingerprint[k];
    const b = current[k];
    if (a == null || b == null) return;
    const std = (norm[k] && norm[k].std) || 1;
    tot += w * Math.pow((a - b) / std, 2);
    wsum += w;
  });
  if (!wsum) return 0;
  return Math.round(100 / (1 + Math.sqrt(tot / wsum)));
}

function AnalogsSection() {
  const symbol = React.useContext(SymbolContext);
  const [data, setData] = React.useState(null);
  const [status, setStatus] = React.useState('loading');
  const [weights, setWeights] = React.useState({});
  const [threshold, setThreshold] = React.useState(70);
  const [overlayCount, setOverlayCount] = React.useState(2);
  const [showBand, setShowBand] = React.useState(true);
  const [histThreshold, setHistThreshold] = React.useState(55);
  const [readoutHorizon, setReadoutHorizon] = React.useState(90);
  const [showModel, setShowModel] = React.useState(true);
  const [fcPath, setFcPath] = React.useState(null);

  // Today's own model forecast (BitMarkAI base scenario) rebased to 100 at now, so it can be
  // overlaid against the historical median path.
  React.useEffect(() => {
    let alive = true;
    setFcPath(null);
    const url = symbol === 'BTC' ? '/api/v1/dashboard' : `/api/v1/dashboard?symbol=${encodeURIComponent(symbol)}`;
    fetch(url, { cache: 'no-store' }).then((r) => r.json()).then((j) => {
      if (!alive || j.status !== 'ready') return;
      const bm = j.bitmark || {};
      const cp = bm.current_price || j.last_close;
      if (!cp || !bm.horizons) return;
      const map = { '1W': 7, '1M': 30, '3M': 90, '6M': 180 };
      const anchors = [{ off: 0, v: 100 }];
      (bm.horizons || []).forEach((h) => {
        const off = map[h.horizon];
        if (off == null || h.type !== 'model' || h.base_low == null || h.base_high == null) return;
        const mid = (h.base_low + h.base_high) / 2;
        anchors.push({ off, v: Math.round((mid / cp) * 1000) / 10 });
      });
      anchors.sort((a, b) => a.off - b.off);
      if (anchors.length > 1) setFcPath(anchors);
    }).catch(() => { /* noop */ });
    return () => { alive = false; };
  }, [symbol]);

  React.useEffect(() => {
    try { const t = parseInt(localStorage.getItem('analog_threshold'), 10); if (t) setThreshold(t); } catch (e) { /* noop */ }
    try { const h = parseInt(localStorage.getItem('analog_hist_threshold'), 10); if (h) setHistThreshold(h); } catch (e) { /* noop */ }
  }, []);
  React.useEffect(() => { try { localStorage.setItem('analog_threshold', String(threshold)); } catch (e) { /* noop */ } }, [threshold]);
  React.useEffect(() => { try { localStorage.setItem('analog_hist_threshold', String(histThreshold)); } catch (e) { /* noop */ } }, [histThreshold]);

  React.useEffect(() => {
    let alive = true;
    setStatus('loading'); setData(null); setWeights({});
    const load = () => fetch(`/api/v1/analogs?symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store' }).then((r) => r.json()).then((j) => {
      if (!alive) return;
      if (j.status === 'ready') {
        setData(j);
        setStatus('ready');
        setWeights((w) => (Object.keys(w).length ? w : Object.fromEntries((j.signals || []).map((s) => [s.key, 1]))));
      } else if (j.status === 'error') { setStatus('error'); } else { setStatus('computing'); }
    }).catch(() => { if (alive) setStatus('error'); });
    load();
    const id = setInterval(() => setStatus((s) => { if (s !== 'ready') load(); return s; }), 5000);
    return () => { alive = false; clearInterval(id); };
  }, [symbol]);

  const ranked = React.useMemo(() => {
    if (!data) return [];
    return data.episodes.map((e) => ({ ...e, match: scoreAnalog(e, data.current, data.norm, weights) })).sort((a, b) => b.match - a.match);
  }, [data, weights]);

  const topEp = ranked[0];
  const overlayEps = React.useMemo(() => ranked.slice(0, overlayCount), [ranked, overlayCount]);
  const overlay = React.useMemo(() => {
    if (!data || !overlayEps.length) return [];
    const cur = Object.fromEntries((data.current_path || []).map((p) => [p.off, p.v]));
    const maps = overlayEps.map((ep) => Object.fromEntries((ep.path || []).map((p) => [p.off, p.v])));
    const offsSet = new Set(Object.keys(cur).map(Number));
    maps.forEach((m) => Object.keys(m).forEach((o) => offsSet.add(Number(o))));
    const offs = Array.from(offsSet).sort((a, b) => a - b);
    return offs.map((o) => {
      const row = { off: o, Today: cur[o] == null ? null : cur[o] };
      maps.forEach((m, idx) => { row[`A${idx}`] = m[o] == null ? null : m[o]; });
      return row;
    });
  }, [data, overlayEps]);

  // Setup History — score every past resolved day against today's setup (respecting live slider
  // weights), keep all above the alert threshold, dedupe nearby clusters, and grade each outcome.
  const setupHistory = React.useMemo(() => {
    if (!data || !data.day_fingerprints) return { rows: [], stats: null };
    const scored = data.day_fingerprints
      .map((d) => ({ ...d, match: scoreAnalog({ fingerprint: d.fp }, data.current, data.norm, weights) }))
      .filter((d) => d.match >= histThreshold)
      .sort((a, b) => (a.date < b.date ? -1 : 1));
    const filtered = [];
    scored.forEach((d) => {
      const last = filtered[filtered.length - 1];
      if (last && Math.abs(new Date(d.date) - new Date(last.date)) < 21 * 864e5) {
        if (d.match > last.match) filtered[filtered.length - 1] = d;
      } else filtered.push(d);
    });
    const resolved = filtered.filter((d) => d.fwd_90 != null);
    const wins = resolved.filter((d) => d.fwd_90 > 0);
    const avg = (arr) => { const a = arr.filter((v) => v != null); return a.length ? Math.round((a.reduce((s, v) => s + v, 0) / a.length) * 10) / 10 : null; };
    const stats = {
      n: filtered.length,
      nResolved: resolved.length,
      winRate: resolved.length ? Math.round((wins.length / resolved.length) * 100) : null,
      avg30: avg(resolved.map((d) => d.fwd_30)),
      avg90: avg(resolved.map((d) => d.fwd_90)),
      avg180: avg(resolved.map((d) => d.fwd_180)),
    };
    return { rows: filtered.slice().sort((a, b) => b.match - a.match), stats };
  }, [data, weights, histThreshold]);

  // Analog Confidence Band — across all matching Setup-History days, gather each day's rebased
  // forward path and compute per-offset percentiles (p10/p25/median/p75/p90). This shades the
  // spread of past outcomes around the overlay so you can see the range at a glance.
  const band = React.useMemo(() => {
    const rows = setupHistory.rows || [];
    if (!showBand || rows.length < 4) return { byOff: {}, color: '#38bdf8', n: rows.length, finalMed: null };
    const pct = (arr, p) => {
      if (!arr.length) return null;
      const s = arr.slice().sort((a, b) => a - b);
      const idx = (s.length - 1) * p;
      const lo = Math.floor(idx); const hi = Math.ceil(idx);
      return lo === hi ? s[lo] : s[lo] + (s[hi] - s[lo]) * (idx - lo);
    };
    const offSet = new Set();
    rows.forEach((r) => (r.fwd_path || []).forEach((p) => { if (p.v != null) offSet.add(p.off); }));
    const byOff = {};
    Array.from(offSet).forEach((off) => {
      const vals = [];
      rows.forEach((r) => { const p = (r.fwd_path || []).find((x) => x.off === off); if (p && p.v != null) vals.push(p.v); });
      if (vals.length < 4) return;
      byOff[off] = { b10: pct(vals, 0.1), b25: pct(vals, 0.25), b50: pct(vals, 0.5), b75: pct(vals, 0.75), b90: pct(vals, 0.9), n: vals.length };
    });
    const offs = Object.keys(byOff).map(Number).sort((a, b) => a - b);
    const finalMed = offs.length ? byOff[offs[offs.length - 1]].b50 : null;
    const color = finalMed == null ? '#38bdf8' : finalMed >= 100 ? '#10b981' : '#f43f5e';
    const atDay = (day) => {
      if (!offs.length) return null;
      if (byOff[day]) return byOff[day];
      if (day < offs[0] || day > offs[offs.length - 1]) return null;
      let lo = offs[0]; let hi = offs[offs.length - 1];
      for (let i = 0; i < offs.length - 1; i += 1) { if (offs[i] <= day && day <= offs[i + 1]) { lo = offs[i]; hi = offs[i + 1]; break; } }
      const a = byOff[lo]; const b = byOff[hi]; const t = (day - lo) / ((hi - lo) || 1);
      const mix = (x, y) => x + (y - x) * t;
      return { b25: mix(a.b25, b.b25), b50: mix(a.b50, b.b50), b75: mix(a.b75, b.b75) };
    };
    const r90 = atDay(90);
    const mkReadout = (day) => { const r = atDay(day); return r ? { lo: Math.round((r.b25 - 100) * 10) / 10, med: Math.round((r.b50 - 100) * 10) / 10, hi: Math.round((r.b75 - 100) * 10) / 10 } : null; };
    const readouts = { 30: mkReadout(30), 90: mkReadout(90), 180: mkReadout(180) };
    const readout = r90 ? { lo: Math.round((r90.b25 - 100) * 10) / 10, med: Math.round((r90.b50 - 100) * 10) / 10, hi: Math.round((r90.b75 - 100) * 10) / 10 } : null;
    return { byOff, color, n: rows.length, finalMed, readout, readouts };
  }, [setupHistory, showBand]);

  // Merge the overlay analog paths with the confidence-band stack fields for the ComposedChart.
  // Band percentiles are stored on a coarse grid (every 12d); we linearly interpolate them onto
  // every chart offset so the stacked areas render as a smooth, gap-free band.
  const chartData = React.useMemo(() => {
    const offs = Object.keys(band.byOff).map(Number).sort((a, b) => a - b);
    const minOff = offs[0]; const maxOff = offs[offs.length - 1];
    const interp = (off) => {
      if (!offs.length || off < minOff || off > maxOff) return null;
      if (band.byOff[off]) return band.byOff[off];
      let lo = offs[0]; let hi = offs[offs.length - 1];
      for (let i = 0; i < offs.length - 1; i += 1) { if (offs[i] <= off && off <= offs[i + 1]) { lo = offs[i]; hi = offs[i + 1]; break; } }
      const a = band.byOff[lo]; const b = band.byOff[hi]; const t = (off - lo) / (hi - lo || 1);
      const mix = (x, y) => x + (y - x) * t;
      return { b10: mix(a.b10, b.b10), b25: mix(a.b25, b.b25), b50: mix(a.b50, b.b50), b75: mix(a.b75, b.b75), b90: mix(a.b90, b.b90) };
    };
    const fcInterp = (off) => {
      if (!showModel || !fcPath || off < 0) return null;
      const a = fcPath;
      if (off < a[0].off || off > a[a.length - 1].off) return null;
      for (let i = 0; i < a.length - 1; i += 1) { if (a[i].off <= off && off <= a[i + 1].off) { const t = (off - a[i].off) / ((a[i + 1].off - a[i].off) || 1); return a[i].v + (a[i + 1].v - a[i].v) * t; } }
      return a[a.length - 1].v;
    };
    return overlay.map((row) => {
      const fc = fcInterp(row.off);
      const withFc = { modelFc: fc == null ? null : Math.round(fc * 10) / 10 };
      const b = interp(row.off);
      if (!b) return { ...row, ...withFc, bandBase: null, bandR1: null, bandR2: null, bandR3: null, bandMed: null };
      return {
        ...row,
        ...withFc,
        bandBase: Math.round(b.b10 * 10) / 10,
        bandR1: Math.round((b.b25 - b.b10) * 10) / 10,
        bandR2: Math.round((b.b75 - b.b25) * 10) / 10,
        bandR3: Math.round((b.b90 - b.b75) * 10) / 10,
        bandMed: Math.round(b.b50 * 10) / 10,
      };
    });
  }, [overlay, band, fcPath, showModel]);
  const bandActive = showBand && Object.keys(band.byOff).length > 0;
  const modelActive = showModel && !!fcPath;

  // Model vs History verdicts — where today's model projection sits within the distribution of
  // past look-alike outcomes at 30 / 90 / 180 days (shown as at-a-glance chips).
  const verdicts = React.useMemo(() => {
    const rows = (setupHistory.rows || []);
    if (!fcPath || rows.length < 4) return [];
    return [30, 90, 180].map((H) => {
      const mv = pathValueAt(fcPath, H);
      if (mv == null) return { H, ok: false };
      const outs = [];
      rows.forEach((r) => { const v = pathValueAt(r.fwd_path, H); if (v != null) outs.push(v); });
      if (outs.length < 4) return { H, ok: false };
      const below = outs.filter((v) => v < mv).length;
      return { H, ok: true, pctBelow: Math.round((below / outs.length) * 100), n: outs.length, modelRet: Math.round((mv - 100) * 10) / 10 };
    });
  }, [fcPath, setupHistory]);

  const sig = (k) => (data ? data.signals.find((s) => s.key === k) : null);
  const fmtSig = (k, v) => {
    if (v == null) return '—';
    const u = sig(k) ? sig(k).unit : '';
    return `${v}${u ? (u === '%' || u === 'pts' || u === 'mo' ? u : ` ${u}`) : ''}`;
  };
  const retColor = (v) => (v == null ? 'text-slate-500' : v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300');
  const closeness = (ep, k) => {
    if (!data) return 2;
    const a = ep.fingerprint[k];
    const b = data.current[k];
    if (a == null || b == null) return null;
    const std = (data.norm[k] && data.norm[k].std) || 1;
    const z = Math.abs((a - b) / std);
    return z < 0.5 ? 0 : z < 1.2 ? 1 : 2;
  };

  return (
    <div className="space-y-6">
      <SectionHead icon={History} title="Happening Again" blurb={sec('analogs').blurb} coin={symbol} />
      <AiReview text={data ? `Today's ${symbol} setup most resembles ${(ranked[0] || {}).label || 'a past episode'} (${(ranked[0] || {}).match || '—'}% match).` : 'Scanning history for the closest analog…'} voice section="analogs" />

      {status === 'ready' && topEp && topEp.match >= threshold && (
        <Card className="border-0 bg-gradient-to-r from-amber-500/15 to-sky-500/10 p-4 ring-1 ring-amber-500/40 animate-in fade-in-0 slide-in-from-top-1 duration-300">
          <div className="flex items-start gap-3">
            <span className="relative mt-0.5 flex h-6 w-6 items-center justify-center">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400/40" />
              <Bell className="relative h-5 w-5 text-amber-300" />
            </span>
            <div className="text-sm">
              <p className="font-bold text-white">Strong setup forming — {topEp.match}% match to {topEp.label}</p>
              <p className="text-slate-300">Back then, {symbol} went on to move <b className={topEp.fwd_90 >= 0 ? 'text-emerald-400' : 'text-red-400'}>{topEp.fwd_90 == null ? '—' : `${topEp.fwd_90 > 0 ? '+' : ''}${topEp.fwd_90}%`}</b> over the next 90 days. Educational pattern-match, not a prediction. <span className="text-slate-500">(A daily bell alert fires automatically at ≥70%.)</span></p>
            </div>
          </div>
        </Card>
      )}

      {status !== 'ready' || !data ? (
        <Card className="border-0 bg-slate-900/60 p-10 text-center ring-1 ring-slate-800">
          <p className="text-sm text-slate-400">{status === 'error' ? 'Could not load the analog engine. Retrying…' : `Scanning ${symbol} history and building fingerprints…`}</p>
        </Card>
      ) : (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="border-0 bg-slate-900/60 p-5 ring-1 ring-slate-800">
              <h3 className="mb-3 text-sm font-bold text-white">Today&apos;s {symbol} setup <span className="text-[11px] font-normal text-slate-500">(as of {data.as_of})</span></h3>
              <div className="space-y-2">
                {data.signals.map((s) => (
                  <div key={s.key} className="flex items-center justify-between gap-2 text-sm">
                    <span className="flex items-center gap-2 text-slate-300">
                      <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${ANALOG_CAT_COLOR[s.cat] || 'bg-slate-700 text-slate-300'}`}>{s.cat}</span>
                      {s.label}
                    </span>
                    <span className="font-semibold text-white">{fmtSig(s.key, data.current[s.key])}</span>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="border-0 bg-slate-900/60 p-5 ring-1 ring-slate-800">
              <div className="mb-3 flex items-center justify-between">
                <TapInfo text="Drag a slider up to make that signal count more when matching today to the past, or down to ignore it. The ranking below updates instantly.">
                  <h3 className="pr-5 text-sm font-bold text-white">Tune what matters</h3>
                </TapInfo>
                <button onClick={() => setWeights(Object.fromEntries(data.signals.map((s) => [s.key, 1])))} className="text-[11px] text-sky-400 hover:text-sky-300">Reset</button>
              </div>
              <div className="space-y-2.5">
                {data.signals.map((s) => (
                  <div key={s.key} className="flex items-center gap-3">
                    <span className="w-40 shrink-0 truncate text-xs text-slate-400">{s.label}</span>
                    <input type="range" min="0" max="3" step="0.5" value={weights[s.key] == null ? 1 : weights[s.key]}
                      onChange={(e) => setWeights((w) => ({ ...w, [s.key]: parseFloat(e.target.value) }))}
                      className="h-1.5 flex-1 cursor-pointer accent-sky-400" />
                    <span className="w-8 shrink-0 text-right text-xs font-semibold text-slate-300">{(weights[s.key] == null ? 1 : weights[s.key]).toFixed(1)}×</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <Card className="border-0 bg-slate-900/60 p-5 ring-1 ring-slate-800">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <TapInfo text="Overlays the top past episodes' price paths (each rebased to 100 at its own setup point) with Bitcoin's recent path (rebased to 100 at today). Left of 0 shows how similar the lead-ins are; each analog line right of 0 shows what happened next.">
                <h3 className="pr-5 text-sm font-bold text-white">Shape overlay · today vs top {overlayCount} analogs</h3>
              </TapInfo>
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-1 text-[11px] text-slate-400">
                  <span>Overlay</span>
                  {[2, 3].map((n) => (
                    <button key={n} onClick={() => setOverlayCount(n)}
                      className={`rounded px-2 py-0.5 text-[11px] font-semibold transition ${overlayCount === n ? 'bg-sky-500/25 text-sky-300 ring-1 ring-sky-500/40' : 'bg-slate-800 text-slate-400 hover:text-slate-200'}`}>
                      Top {n}
                    </button>
                  ))}
                </div>
                <button onClick={() => setShowBand((v) => !v)}
                  className={`rounded px-2 py-0.5 text-[11px] font-semibold transition ${showBand ? 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40' : 'bg-slate-800 text-slate-400 hover:text-slate-200'}`}>
                  Outcome band {showBand ? 'on' : 'off'}
                </button>
                <button onClick={() => setShowModel((v) => !v)} disabled={!fcPath}
                  className={`rounded px-2 py-0.5 text-[11px] font-semibold transition disabled:opacity-40 ${showModel ? 'bg-white/15 text-slate-100 ring-1 ring-white/30' : 'bg-slate-800 text-slate-400 hover:text-slate-200'}`}>
                  Model forecast {showModel ? 'on' : 'off'}
                </button>
                <div className="flex items-center gap-2 text-[11px] text-slate-400">
                  <Bell className="h-3.5 w-3.5 text-amber-300" />
                  <span>Alert me at ≥</span>
                  <input type="range" min="50" max="90" step="5" value={threshold} onChange={(e) => setThreshold(parseInt(e.target.value, 10))} className="h-1.5 w-24 cursor-pointer accent-amber-400" />
                  <span className="w-8 font-semibold text-amber-300">{threshold}%</span>
                </div>
              </div>
            </div>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 6, right: 12, left: -14, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="off" type="number" domain={['dataMin', 'dataMax']} stroke="#64748b" fontSize={11} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}d`} />
                  <YAxis stroke="#64748b" fontSize={11} domain={['auto', 'auto']} tickFormatter={(v) => Math.round(v)} />
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} labelFormatter={(v) => `${v > 0 ? '+' : ''}${v} days from setup`} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <ReferenceLine x={0} stroke="#64748b" strokeDasharray="4 4" />
                  <ReferenceLine y={100} stroke="#334155" strokeDasharray="3 3" />
                  {bandActive && <Area dataKey="bandBase" stackId="band" stroke="none" fill="transparent" connectNulls isAnimationActive={false} legendType="none" tooltipType="none" activeDot={false} />}
                  {bandActive && <Area dataKey="bandR1" stackId="band" stroke="none" fill={band.color} fillOpacity={0.08} connectNulls isAnimationActive={false} name="Past range (10–90%)" activeDot={false} />}
                  {bandActive && <Area dataKey="bandR2" stackId="band" stroke="none" fill={band.color} fillOpacity={0.2} connectNulls isAnimationActive={false} name="Middle 50% of outcomes" activeDot={false} />}
                  {bandActive && <Area dataKey="bandR3" stackId="band" stroke="none" fill={band.color} fillOpacity={0.08} connectNulls isAnimationActive={false} legendType="none" tooltipType="none" activeDot={false} />}
                  {bandActive && <Line type="monotone" dataKey="bandMed" stroke={band.color} strokeWidth={1.6} strokeDasharray="5 4" dot={false} connectNulls name="Median past outcome" />}
                  {overlayEps.map((ep, idx) => (
                    <Line key={ep.id} type="monotone" dataKey={`A${idx}`} stroke={ANALOG_OVERLAY_COLORS[idx % ANALOG_OVERLAY_COLORS.length]} strokeWidth={2} dot={false} connectNulls name={`${ep.label} (${ep.match}%)`} />
                  ))}
                  {modelActive && <Line type="monotone" dataKey="modelFc" stroke="#f8fafc" strokeWidth={2} strokeDasharray="2 3" dot={false} connectNulls name="Today’s model (base)" />}
                  <Line type="monotone" dataKey="Today" stroke="#38bdf8" strokeWidth={2.6} dot={false} connectNulls name={`${symbol} now`} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-[11px] text-slate-500">
              Each line is rebased to 100 at its own “now / setup” point (day 0). Left of 0 = the lead-in shapes; right of 0 = how each analog played out afterward.
              {bandActive
                ? <> The shaded {band.color === '#10b981' ? 'green' : band.color === '#f43f5e' ? 'red' : ''} band shows the spread of ALL {band.n} matching past setups: the darker core is the middle 50% of outcomes, the lighter halo the 10–90% range, and the dashed line the median path.</>
                : <> Turn on “Outcome band” to shade the range of every past matching setup around these paths.</>}
              {modelActive && <> The white dotted line is BTCIQ’s own base-case forecast for today — see where the model sits versus what history did.</>}
            </p>
            {bandActive && (
              <div className="mt-2 rounded-lg bg-slate-950/50 px-3 py-2 text-xs text-slate-300 ring-1 ring-slate-800">
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <span className="font-semibold text-white">In plain English</span>
                  <div className="flex items-center gap-1 text-[11px] text-slate-400">
                    <span>at</span>
                    {[30, 90, 180].map((hz) => (
                      <button key={hz} onClick={() => setReadoutHorizon(hz)}
                        className={`rounded px-1.5 py-0.5 font-semibold transition ${readoutHorizon === hz ? 'bg-sky-500/25 text-sky-300 ring-1 ring-sky-500/40' : 'bg-slate-800 text-slate-400 hover:text-slate-200'}`}>
                        {hz}d
                      </button>
                    ))}
                  </div>
                </div>
                {band.readouts[readoutHorizon] ? (
                  <p>
                    Across the {band.n} past setups like today, the middle 50% landed between{' '}
                    <b className={band.readouts[readoutHorizon].lo >= 0 ? 'text-emerald-400' : 'text-red-400'}>{band.readouts[readoutHorizon].lo > 0 ? '+' : ''}{band.readouts[readoutHorizon].lo}%</b> and{' '}
                    <b className={band.readouts[readoutHorizon].hi >= 0 ? 'text-emerald-400' : 'text-red-400'}>{band.readouts[readoutHorizon].hi > 0 ? '+' : ''}{band.readouts[readoutHorizon].hi}%</b> at {readoutHorizon} days (median{' '}
                    <b className={band.readouts[readoutHorizon].med >= 0 ? 'text-emerald-400' : 'text-red-400'}>{band.readouts[readoutHorizon].med > 0 ? '+' : ''}{band.readouts[readoutHorizon].med}%</b>).
                  </p>
                ) : (
                  <p className="text-slate-500">Not enough resolved history at {readoutHorizon} days for this setup — try a shorter horizon or a looser match level.</p>
                )}
                {modelActive && verdicts.length > 0 && (
                  <div className="mt-2 border-t border-slate-800 pt-2">
                    <span className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold text-white">
                      Model vs history
                      <InfoTip below={false} text="For each horizon we take BTCIQ's own base-case price, rebase it to 100 like the chart, and rank it against the matching past setups' actual outcomes at that horizon. “bearish X%” means the model projects a lower result than X% of those look-alikes; “bullish X%” means higher than X% of them." />
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {verdicts.map((v) => (v.ok ? (
                        <div key={v.H} className="flex items-center gap-1.5 rounded-lg bg-slate-900/80 px-2.5 py-1 ring-1 ring-slate-800">
                          <span className="text-[11px] font-bold text-slate-400">{v.H}d</span>
                          <span className={`text-[11px] font-semibold ${v.modelRet >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{v.modelRet > 0 ? '+' : ''}{v.modelRet}%</span>
                          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${v.pctBelow >= 50 ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'}`}>
                            {v.pctBelow >= 50 ? `bullish ${v.pctBelow}%` : `bearish ${100 - v.pctBelow}%`}
                          </span>
                        </div>
                      ) : (
                        <div key={v.H} className="flex items-center gap-1.5 rounded-lg bg-slate-900/50 px-2.5 py-1 text-[11px] text-slate-600 ring-1 ring-slate-800">{v.H}d · n/a</div>
                      )))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>

          <Card className="border-0 bg-slate-900/60 p-5 ring-1 ring-slate-800">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <TapInfo text="A backtest of today's setup: every past day whose conditions matched today (at or above the match level below, using the same slider weights) is listed here with what Bitcoin did next. The win rate is the share of those days that were higher 90 days later.">
                <h3 className="pr-5 text-sm font-bold text-white">Setup history · when this happened before</h3>
              </TapInfo>
              <div className="flex items-center gap-2 text-[11px] text-slate-400">
                <span>Match ≥</span>
                <input type="range" min="40" max="80" step="5" value={histThreshold} onChange={(e) => setHistThreshold(parseInt(e.target.value, 10))} className="h-1.5 w-24 cursor-pointer accent-sky-400" />
                <span className="w-8 font-semibold text-sky-300">{histThreshold}%</span>
              </div>
            </div>
            {setupHistory.rows.length === 0 ? (
              <p className="py-6 text-center text-sm text-slate-500">No past days reach the {histThreshold}% match level. Lower the “Match ≥” level or ease the slider weights to surface looser analogs.</p>
            ) : (
              <>
                <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="rounded-lg bg-slate-950/50 p-3 text-center">
                    <p className="text-2xl font-black text-white">{setupHistory.stats.n}</p>
                    <p className="text-[9px] uppercase tracking-wider text-slate-500">matching days</p>
                  </div>
                  <div className="rounded-lg bg-slate-950/50 p-3 text-center">
                    <p className="text-2xl font-black" style={{ color: setupHistory.stats.winRate == null ? '#94a3b8' : setupHistory.stats.winRate >= 50 ? '#34d399' : '#f87171' }}>{setupHistory.stats.winRate == null ? '—' : `${setupHistory.stats.winRate}%`}</p>
                    <p className="text-[9px] uppercase tracking-wider text-slate-500">higher after 90d</p>
                  </div>
                  <div className="rounded-lg bg-slate-950/50 p-3 text-center">
                    <p className={`text-2xl font-black ${retColor(setupHistory.stats.avg90)}`}>{setupHistory.stats.avg90 == null ? '—' : `${setupHistory.stats.avg90 > 0 ? '+' : ''}${setupHistory.stats.avg90}%`}</p>
                    <p className="text-[9px] uppercase tracking-wider text-slate-500">avg 90d move</p>
                  </div>
                  <div className="rounded-lg bg-slate-950/50 p-3 text-center">
                    <p className={`text-2xl font-black ${retColor(setupHistory.stats.avg180)}`}>{setupHistory.stats.avg180 == null ? '—' : `${setupHistory.stats.avg180 > 0 ? '+' : ''}${setupHistory.stats.avg180}%`}</p>
                    <p className="text-[9px] uppercase tracking-wider text-slate-500">avg 180d move</p>
                  </div>
                </div>
                <div className="max-h-72 overflow-y-auto rounded-lg ring-1 ring-slate-800">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-slate-900/95 text-[10px] uppercase tracking-wider text-slate-500">
                      <tr>
                        <th className="px-3 py-2 text-left font-semibold">Date</th>
                        <th className="px-3 py-2 text-right font-semibold">Match</th>
                        <th className="px-3 py-2 text-center font-semibold">Path (0→180d)</th>
                        <th className="px-3 py-2 text-right font-semibold">+30d</th>
                        <th className="px-3 py-2 text-right font-semibold">+90d</th>
                        <th className="px-3 py-2 text-right font-semibold">+180d</th>
                        <th className="px-3 py-2 text-right font-semibold">Outcome</th>
                      </tr>
                    </thead>
                    <tbody>
                      {setupHistory.rows.map((r) => {
                        const win = r.fwd_90 == null ? null : r.fwd_90 > 0;
                        return (
                          <tr key={r.date} className="border-t border-slate-800/70">
                            <td className="px-3 py-2 text-slate-300">{r.date}</td>
                            <td className="px-3 py-2 text-right font-semibold" style={{ color: r.match >= 80 ? '#34d399' : r.match >= 70 ? '#38bdf8' : '#94a3b8' }}>{r.match}%</td>
                            <td className="px-3 py-2 text-center"><OutcomeSpark points={r.fwd_path} color={win == null ? '#64748b' : win ? '#34d399' : '#f87171'} /></td>
                            <td className={`px-3 py-2 text-right ${retColor(r.fwd_30)}`}>{r.fwd_30 == null ? '—' : `${r.fwd_30 > 0 ? '+' : ''}${r.fwd_30}%`}</td>
                            <td className={`px-3 py-2 text-right ${retColor(r.fwd_90)}`}>{r.fwd_90 == null ? '—' : `${r.fwd_90 > 0 ? '+' : ''}${r.fwd_90}%`}</td>
                            <td className={`px-3 py-2 text-right ${retColor(r.fwd_180)}`}>{r.fwd_180 == null ? '—' : `${r.fwd_180 > 0 ? '+' : ''}${r.fwd_180}%`}</td>
                            <td className="px-3 py-2 text-right">
                              {win == null ? <span className="text-slate-500">open</span>
                                : <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${win ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'}`}>{win ? 'WIN' : 'LOSS'}</span>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <p className="mt-3 text-[11px] italic text-slate-500">“Win” = Bitcoin was higher 90 days later. Sampled from ~10 years of daily data (a small sample) and de-duplicated so clustered days count once. Educational pattern-matching, not a prediction or financial advice.</p>
              </>
            )}
          </Card>

          <div>
            <h3 className="mb-3 text-sm font-bold text-white">Closest historical analogs</h3>
            <div className="grid gap-4 md:grid-cols-2">
              {ranked.slice(0, 6).map((ep) => {
                const up = ep.type === 'rally';
                return (
                  <Card key={ep.id} className="border-0 bg-slate-900/60 p-4 ring-1 ring-slate-800">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="flex items-center gap-2 font-bold text-white">
                          <span className={up ? 'text-emerald-400' : 'text-red-400'}>{up ? '▲' : '▼'}</span>{ep.label}
                        </p>
                        <p className="text-[11px] text-slate-500">{ep.start} → {ep.end} · {ep.duration_days}d</p>
                      </div>
                      <div className="text-right">
                        <p className="text-2xl font-black" style={{ color: ep.match >= 70 ? '#34d399' : ep.match >= 50 ? '#38bdf8' : '#94a3b8' }}>{ep.match}%</p>
                        <p className="text-[9px] uppercase tracking-wider text-slate-500">match</p>
                      </div>
                    </div>

                    {ep.tags && ep.tags.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {ep.tags.map((t, i) => (
                          <span key={i} className={`rounded px-1.5 py-0.5 text-[9px] font-semibold ${ANALOG_CAT_COLOR[t.cat] || 'bg-slate-700 text-slate-300'}`}>{t.label}</span>
                        ))}
                      </div>
                    )}

                    <div className="mt-3 grid grid-cols-3 gap-2 rounded-lg bg-slate-950/50 p-2 text-center">
                      {[['30d', ep.fwd_30], ['90d', ep.fwd_90], ['180d', ep.fwd_180]].map(([lbl, v]) => (
                        <div key={lbl}>
                          <p className="text-[9px] uppercase text-slate-500">then +{lbl}</p>
                          <p className={`text-sm font-bold ${retColor(v)}`}>{v == null ? '—' : `${v > 0 ? '+' : ''}${v}%`}</p>
                        </div>
                      ))}
                    </div>

                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {data.signals.map((s) => {
                        const c = closeness(ep, s.key);
                        const col = c === 0 ? 'bg-emerald-500/20 text-emerald-300' : c === 1 ? 'bg-amber-500/20 text-amber-300' : 'bg-red-500/15 text-red-300';
                        return <span key={s.key} title={`${s.label}: then ${fmtSig(s.key, ep.fingerprint[s.key])} vs now ${fmtSig(s.key, data.current[s.key])}`} className={`rounded px-1.5 py-0.5 text-[9px] font-medium ${col}`}>{s.label.split(' ')[0]}{c === 0 ? ' ✓' : ''}</span>;
                      })}
                    </div>
                  </Card>
                );
              })}
            </div>
            <p className="mt-3 text-[11px] italic text-slate-500">Green = that condition closely matches today; amber = somewhat; red = quite different. Based on ~10 years of data — a small sample. Educational pattern-matching, not a prediction or financial advice.</p>
          </div>
        </>
      )}
    </div>
  );
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
    const load = () => fetch(`/api/v1/markets?symbol=${encodeURIComponent(symbol)}&window=${window}`, { cache: 'no-store' })
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
            className={`rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${window === k ? 'bg-sky-500/20 text-sky-200 ring-1 ring-sky-500/40' : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'}`}>{lbl}</button>
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

function CompareOverlay({ coinData, coinSymbol, coinName, onClose }) {
  const [btc, setBtc] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    let alive = true;
    fetch('/api/v1/dashboard', { cache: 'no-store' }).then((r) => r.json())
      .then((j) => { if (alive && j.status === 'ready') setBtc(j); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  const horizons = [['24H', '24-Hour'], ['7D', '7-Day'], ['30D', '30-Day']];
  const getf = (dd, h) => ((dd && dd.forecasts) || []).find((x) => x.horizon === h);
  const chartData = btc ? horizons.map(([h, lbl]) => {
    const b = getf(btc, h); const c = getf(coinData, h);
    return { horizon: lbl, Bitcoin: b ? b.higher : null, [coinName]: c ? c.higher : null };
  }) : [];

  const Col = ({ dd, name, sym }) => {
    const qs = dd ? dd.quant_score : null;
    return (
      <div className="flex-1 rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-center">
        <div className="flex items-center justify-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-800 text-[10px] font-black text-sky-300">{sym}</span>
          <p className="text-sm font-bold text-white">{name}</p>
        </div>
        <p className="mt-3 text-4xl font-black" style={{ color: qs != null ? scoreColor(qs) : '#94a3b8' }}>{qs != null ? qs : '—'}</p>
        <p className="text-xs text-slate-400">{(dd && dd.quant_label) || 'Quant Score'}</p>
        <div className="mt-3 space-y-1 text-left text-xs text-slate-300">
          <p><span className="text-slate-500">Regime:</span> {(dd && dd.regime && dd.regime.regime) || '—'}</p>
          <p><span className="text-slate-500">Next-day:</span> {(dd && dd.signal) || '—'} {dd && dd.confidence ? `(${dd.confidence}%)` : ''}</p>
          <p><span className="text-slate-500">Market share:</span> {dd && dd.dominance ? `${dd.dominance.dominance}%` : '—'}</p>
        </div>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-[140] flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-2xl animate-in fade-in-0 zoom-in-95 duration-200" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2"><Scale className="h-5 w-5 text-sky-400" /><h2 className="text-lg font-bold text-white">{coinName} vs Bitcoin</h2></div>
          <button onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white"><X className="h-5 w-5" /></button>
        </div>
        {loading && !btc ? (
          <p className="py-10 text-center text-sm text-slate-400">Loading Bitcoin data…</p>
        ) : (
          <>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Col dd={btc} name="Bitcoin" sym="BTC" />
              <Col dd={coinData} name={coinName} sym={coinSymbol} />
            </div>
            <div className="mt-5">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Probability of closing higher (%)</p>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="horizon" stroke="#64748b" fontSize={12} />
                    <YAxis domain={[0, 100]} stroke="#64748b" fontSize={12} />
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} cursor={{ fill: 'rgba(148,163,184,0.08)' }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="Bitcoin" fill="#f7931a" radius={[4, 4, 0, 0]} />
                    <Bar dataKey={coinName} fill="#38bdf8" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <p className="mt-3 text-[11px] italic text-slate-500">Higher % = the model&apos;s estimated chance of a higher close over that horizon. Odds, not certainty — not financial advice.</p>
          </>
        )}
      </div>
    </div>
  );
}

function CoinPicker({ coins, symbol, onSelect }) {
  const [open, setOpen] = React.useState(false);
  const current = coins.find((c) => c.symbol === symbol) || { symbol, name: symbol };
  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)} title="Switch coin — the whole dashboard follows"
        className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-sm font-semibold text-white transition-colors ${open ? 'border-sky-500/60 bg-slate-800' : 'border-slate-700 bg-slate-900 hover:border-sky-500/50'}`}>
        <CoinIcon symbol={current.symbol} size={24} />
        <span className="hidden sm:inline">{current.name}</span>
        <ChevronDown className={`h-4 w-4 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-[90]" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-full z-[100] mt-2 max-h-[70vh] w-56 overflow-auto rounded-xl border border-slate-700 bg-slate-900 p-1.5 shadow-2xl animate-in fade-in-0 zoom-in-95 slide-in-from-top-1 duration-150">
            <p className="px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Choose an asset</p>
            {coins.map((c) => (
              <button key={c.symbol} onClick={() => { onSelect(c.symbol); setOpen(false); }}
                className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors ${c.symbol === symbol ? 'bg-sky-500/15 text-sky-200' : 'text-slate-300 hover:bg-slate-800'}`}>
                <CoinIcon symbol={c.symbol} size={24} />
                <span className="flex-1">{c.name}</span>
                {c.symbol === 'BTC' && <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-bold text-amber-300">FULL</span>}
                {c.symbol === symbol && <Check className="h-3.5 w-3.5 text-sky-300" />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const [symbol, setSymbol] = useState('BTC');
  const [coins, setCoins] = useState([{ symbol: 'BTC', name: 'Bitcoin' }]);
  const [data, setData] = useState(__dashCache);
  const [status, setStatus] = useState(__dashCache ? 'ready' : 'loading');
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [ticker, setTicker] = useState(__tickerCache);
  const [active, setActive] = useState('overview');
  const [showReport, setShowReport] = useState(false);
  const [news, setNews] = useState(__newsCache);
  const [newsStatus, setNewsStatus] = useState(__newsCache ? 'ready' : 'loading');
  const [newsRefreshing, setNewsRefreshing] = useState(false);
  const [alertsData, setAlertsData] = useState(__alertsCache);
  const [alertFilter, setAlertFilter] = useState('BTC');
  const [compareOpen, setCompareOpen] = useState(false);
  const firstSym = React.useRef(true);

  // Restore last-picked coin + load the supported coin list.
  useEffect(() => {
    try { const s = (localStorage.getItem('btciq_symbol') || '').toUpperCase(); if (s) setSymbol(s); } catch (e) { /* noop */ }
    fetch('/api/v1/compare/coins').then((r) => r.json()).then((j) => { if (j.coins) setCoins([{ symbol: 'BTC', name: 'Bitcoin' }, ...j.coins.filter((c) => c.symbol !== 'BTC')]); }).catch(() => {});
  }, []);

  // Persist choice + reset the view whenever the coin changes so we never show a stale asset.
  useEffect(() => {
    try { localStorage.setItem('btciq_symbol', symbol); } catch (e) { /* noop */ }
    if (firstSym.current) { firstSym.current = false; return; }
    const btc = symbol === 'BTC';
    setData(btc ? (__dashCache || null) : null);
    setStatus(btc && __dashCache ? 'ready' : 'loading');
    setError(null);
    setNews(btc ? (__newsCache || null) : null);
    setNewsStatus(btc && __newsCache ? 'ready' : 'loading');
    setTicker(btc ? (__tickerCache || null) : null);
    // if the current section is hidden for altcoins, jump back to Overview
    setActive((a) => (!btc && BTC_ONLY_SECTIONS.includes(a) ? 'overview' : a));
    if (btc) setCompareOpen(false);
  }, [symbol]);

  // Keep the Alerts feed scoped to the coin the user is viewing (they can still switch to All/other coins in the Alerts screen).
  useEffect(() => { setAlertFilter(symbol); }, [symbol]);

  // Reflect the selected coin in the browser tab (favicon + title).
  useEffect(() => {
    const coin = coins.find((c) => c.symbol === symbol);
    const name = (coin && coin.name) || (data && data.coin_name) || symbol;
    const price = ticker && ticker.price;
    document.title = price ? `${symbol} ${fmtUsd(price)} · BTCIQ` : `${name} · BTCIQ`;
    try {
      const href = `https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/${symbol.toLowerCase()}.png`;
      const links = document.querySelectorAll("link[rel~='icon'], link[rel='shortcut icon'], link[rel='apple-touch-icon']");
      if (links.length) { links.forEach((l) => { l.href = href; }); }
      else { const l = document.createElement('link'); l.rel = 'icon'; l.href = href; document.head.appendChild(l); }
    } catch (e) { /* noop */ }
  }, [symbol, ticker, coins, data]);


  const symQs = (base) => (symbol === 'BTC' ? base : `${base}${base.includes('?') ? '&' : '?'}symbol=${encodeURIComponent(symbol)}`);

  const loadAlerts = useCallback(async () => {
    try {
      const q = alertFilter && alertFilter !== 'ALL' ? `?symbol=${encodeURIComponent(alertFilter)}` : '';
      const r = await fetch(`/api/v1/alerts${q}`, { cache: 'no-store' });
      const j = await r.json();
      if (j.status === 'ready') { __alertsCache = j; setAlertsData(j); }
    } catch (e) { /* noop */ }
  }, [alertFilter]);

  const ackAlerts = useCallback(async (ids) => {
    try {
      const body = ids ? { ids } : (alertFilter && alertFilter !== 'ALL' ? { symbol: alertFilter } : {});
      await fetch('/api/v1/alerts/ack', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      loadAlerts();
    } catch (e) { /* noop */ }
  }, [loadAlerts, alertFilter]);

  useEffect(() => {
    loadAlerts();
    const id = setInterval(loadAlerts, 30000);
    return () => clearInterval(id);
  }, [loadAlerts]);

  const loadNews = useCallback(async () => {
    try {
      const r = await fetch(symbol === 'BTC' ? '/api/v1/news' : `/api/v1/news?symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store' });
      const j = await r.json();
      if (j.status === 'ready') { if (symbol === 'BTC') __newsCache = j; setNews(j); setNewsStatus('ready'); setNewsRefreshing(false); }
      else setNewsStatus(j.status || 'computing');
    } catch (e) { setNewsStatus('error'); }
  }, [symbol]);

  useEffect(() => {
    loadNews();
    const id = setInterval(() => { setNewsStatus((s) => { if (s !== 'ready') loadNews(); return s; }); }, 5000);
    return () => clearInterval(id);
  }, [loadNews]);

  const handleNewsRefresh = async () => {
    if (symbol !== 'BTC') { loadNews(); return; }
    setNewsRefreshing(true);
    await fetch('/api/v1/news/refresh', { method: 'POST' });
    const id = setInterval(loadNews, 5000);
    setTimeout(() => clearInterval(id), 70000);
  };

  const load = useCallback(async () => {
    try {
      const res = await fetch(symbol === 'BTC' ? '/api/v1/dashboard' : `/api/v1/dashboard?symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store' });
      const json = await res.json();
      if (json.status === 'ready') { if (symbol === 'BTC') __dashCache = json; setData(json); setStatus('ready'); setRefreshing(false); }
      else if (json.status === 'error') { setError(json.error || 'Unknown error'); setStatus('error'); }
      else setStatus('computing');
    } catch (e) { setError(String(e)); setStatus('error'); }
  }, [symbol]);

  useEffect(() => {
    load();
    const id = setInterval(() => { setStatus((s) => { if (s !== 'ready') load(); return s; }); }, 4000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    let alive = true;
    const loadTicker = async () => {
      try { const r = await fetch(symbol === 'BTC' ? '/api/v1/ticker' : `/api/v1/ticker?symbol=${encodeURIComponent(symbol)}`, { cache: 'no-store' }); const j = await r.json(); if (alive && j && j.price) { if (symbol === 'BTC') __tickerCache = j; setTicker(j); } } catch (e) { /* noop */ }
    };
    loadTicker();
    const t = setInterval(loadTicker, 10000);
    const dref = setInterval(() => load(), 60000);
    return () => { alive = false; clearInterval(t); clearInterval(dref); };
  }, [load, symbol]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetch('/api/v1/refresh', { method: 'POST' });
    const id = setInterval(load, 4000);
    setTimeout(() => clearInterval(id), 90000);
  };

  if (!data && (status === 'loading' || status === 'computing')) {
    return <DashboardSkeleton ticker={ticker} />;
  }
  if (!data && status === 'error') {
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
  const activeSection = sec(active);
  const visibleSections = SECTIONS.filter((s) => !REMOVED_SECTIONS.includes(s.id) && (symbol === 'BTC' || !BTC_ONLY_SECTIONS.includes(s.id)));
  const renderSection = () => {
    if (active === 'overview') return <OverviewSection d={d} ticker={ticker} />;
    if (active === 'forecasts') return <ForecastsHubSection d={d} />;
    if (active === 'market-intel') return <MarketIntelligenceSection d={d} />;
    if (active === 'crossmarket') return <CrossMarketSection />;
    if (active === 'analogs') return <AnalogsSection />;
    if (active === 'smartmoney') return <DemoMetricsCard title="Smart Money" icon={Waves} panel={d.smart_money} sectionId="smartmoney" />;
    if (active === 'whales') return <WhaleWatch />;
    if (active === 'network') return <NetworkSentimentSection />;
    if (active === 'dataaudit') return <DataAuditSection />;
    if (active === 'admin') return <AdminSection />;
    if (active === 'leverage') return <LeverageSection />;
    if (active === 'institutional') return (<div className="space-y-5"><DemoMetricsCard title="Institutional & Derivatives" icon={Landmark} panel={d.institutional} sectionId="institutional" />{(d.symbol || 'BTC') === 'BTC' && <EtfFlowsCard />}</div>);
    if (active === 'macro') return <PolicySection d={d} />;
    if (active === 'news') return <NewsSection news={news} status={newsStatus} onRefresh={handleNewsRefresh} refreshing={newsRefreshing} />;
    if (active === 'risk') return <RiskSection d={d} />;
    if (active === 'events') return <EventsSection d={d} />;
    if (active === 'performance') return <PerformanceHubSection d={d} />;
    if (active === 'timemachine') return <TimeMachineSection />;
    if (active === 'ask') return <AskQuantSection d={d} />;
    if (active === 'alerts') return <AlertsSection d={d} alertsData={alertsData} onAck={ackAlerts} filter={alertFilter} onFilter={setAlertFilter} coins={coins} />;
    if (active === 'settings') return <SettingsSection />;
    return <ComingSoonSection section={activeSection} />;
  };

  return (
    <SymbolContext.Provider value={symbol}>
    <div className="relative min-h-screen bg-slate-950 text-slate-100">
      <div aria-hidden className="pointer-events-none fixed inset-0 bg-[radial-gradient(55rem_38rem_at_-8%_-12%,rgba(247,147,26,0.10),transparent_58%),radial-gradient(52rem_40rem_at_112%_6%,rgba(109,94,246,0.14),transparent_55%)]" />
      {compareOpen && symbol !== 'BTC' && d && (
        <CompareOverlay coinData={d} coinSymbol={symbol} coinName={(coins.find((c) => c.symbol === symbol) || {}).name || symbol} onClose={() => setCompareOpen(false)} />
      )}
      <div className="relative flex">
        {/* Sidebar */}
        <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-slate-800/80 bg-slate-900/40 p-4 backdrop-blur-sm md:flex">
          <div className="mb-6 flex flex-col gap-1 px-1">
            <img src="/btciq-logo.png" alt="BTCIQ" className="h-11 w-auto object-contain" />
            <p className="pl-0.5 text-[11px] font-semibold">
              <span className="bg-gradient-to-r from-amber-400 via-sky-400 to-violet-400 bg-clip-text text-transparent">BTCIQ</span>
              <span className="text-slate-500"> · Powered by BitCentAI</span>
            </p>
          </div>
          <nav className="flex-1 space-y-1">
            {visibleSections.map((s) => {
              const Icon = s.icon;
              const on = active === s.id;
              return (
                <button key={s.id} onClick={() => setActive(s.id)}
                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${on ? 'bg-gradient-to-r from-sky-500/20 via-violet-500/12 to-transparent font-semibold text-white ring-1 ring-sky-500/25' : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'}`}>
                  <Icon className="h-4 w-4" />{s.label}
                  {s.soon && <Lock className="ml-auto h-3 w-3 text-slate-600" />}
                </button>
              );
            })}
          </nav>
          <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
            <div className="flex items-center justify-between"><span className="text-[10px] uppercase text-slate-500">Quant Score</span><span className="text-[10px] text-slate-500">{d.data_source}</span></div>
            <div className="mt-1 flex items-center gap-2"><span className="text-2xl font-black" style={{ color: scoreColor(d.quant_score) }}>{d.quant_score}</span><span className="text-xs text-slate-400">{d.quant_label}</span></div>
          </div>
          <a href="https://btciq.app" target="_blank" rel="noopener noreferrer" className="mt-3 flex items-center justify-center gap-1 text-[11px] font-semibold text-slate-500 transition-colors hover:text-sky-300">
            <Globe className="h-3 w-3" />btciq.app
          </a>
        </aside>

        {/* Main */}
        <div className="min-w-0 flex-1">
          {/* Top bar */}
          <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-slate-800 bg-slate-950/80 px-4 py-3 backdrop-blur md:px-8">
            <div className="flex items-center gap-2 md:hidden"><img src="/btciq-logo.png" alt="BTCIQ" className="h-6 w-auto object-contain" /></div>
            <CoinPicker coins={coins} symbol={symbol} onSelect={setSymbol} />
            {symbol !== 'BTC' && (
              <button onClick={() => setCompareOpen(true)} title="Overlay this coin vs Bitcoin"
                className="flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-200 transition-colors hover:border-sky-500/50 hover:text-sky-200">
                <Scale className="h-4 w-4" /><span className="hidden sm:inline">vs Bitcoin</span>
              </button>
            )}
            <div className="hidden items-center gap-2 md:flex">
              <span className="flex items-center gap-1 text-xs font-bold text-emerald-400">
                <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" /><span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" /></span>LIVE
              </span>
              <span className="text-lg font-bold text-white">{fmtUsd(ticker?.price ?? d.last_close)}</span>
              {ticker?.price_aud && <span className="rounded-md bg-amber-500/10 px-1.5 py-0.5 text-xs font-semibold text-amber-300 ring-1 ring-amber-500/20">≈ {fmtAud(ticker.price_aud)}</span>}
              <span className={`text-sm font-semibold ${(ticker?.change24h ?? d.day_change_pct) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{ticker?.change24h ?? d.day_change_pct}%</span>
            </div>
            <button onClick={() => setActive('alerts')} title="Smart Alerts"
              className="relative ml-auto rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200">
              <Bell className="h-5 w-5" />
              {alertsData?.unseen > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">{alertsData.unseen > 9 ? '9+' : alertsData.unseen}</span>
              )}
            </button>
            <Button onClick={() => setShowReport(true)} size="sm" variant="outline" title="Shareable daily report"
              className="gap-1.5 border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800">
              <ClipboardList className="h-4 w-4" /><span className="hidden sm:inline">Report</span>
            </Button>
            <Button onClick={handleRefresh} disabled={refreshing} size="sm" className="gap-2 bg-gradient-to-r from-sky-500 to-violet-600 text-white shadow-lg shadow-violet-500/20 hover:from-sky-400 hover:to-violet-500">
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />{refreshing ? 'Retraining' : 'Retrain'}
            </Button>
          </div>

          {/* Mobile nav */}
          <div className="flex gap-1 overflow-x-auto border-b border-slate-800 px-3 py-2 md:hidden">
            {visibleSections.map((s) => (
              <button key={s.id} onClick={() => setActive(s.id)} className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-xs ${active === s.id ? 'bg-sky-500/15 font-semibold text-sky-300' : 'text-slate-400'}`}>{s.label}</button>
            ))}
          </div>

          <main className="mx-auto max-w-6xl px-4 py-6 md:px-8"><ErrorBoundary label={activeSection?.label || active} resetKey={active}>{renderSection()}</ErrorBoundary></main>
          <footer className="space-y-2 px-4 pb-8 text-center md:px-8">
            <p className="mx-auto max-w-3xl rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-2.5 text-[11px] leading-relaxed text-slate-500">
              BTCIQ provides Bitcoin market analysis, probability-based forecasts and educational information. It does not provide personalised financial advice or guarantee future outcomes.
            </p>
            <p className="text-xs text-slate-600">BTCIQ — Bitcoin Market Analysis · powered by BitCentAI · BitMarkAI forecast engine · real data via {d.data_source}</p>
          </footer>
        </div>
      </div>
    </div>
    <FloatingAlbert active={active} symbol={symbol} onExpand={() => setActive('ask')} />
    {showReport && <DailyReportModal d={d} onClose={() => setShowReport(false)} />}
    </SymbolContext.Provider>
  );
}
