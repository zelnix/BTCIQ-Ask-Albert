'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  ResponsiveContainer, ComposedChart, Line, Area, Bar, BarChart,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell,
} from 'recharts';
import {
  TrendingUp, TrendingDown, RefreshCw, Activity, Gauge, Waves, BarChart3,
  ArrowUpRight, ArrowDownRight, Cpu, Database, Trophy, Radio, History,
  Check, X, LayoutDashboard, Target, FlaskConical, Bell, MessageCircle,
  Sparkles, Info, Lock, Compass, CandlestickChart, Layers, Landmark, Globe, Newspaper,
  Brain, Send, ShieldAlert, Scale, CalendarClock, ClipboardList, ShieldCheck,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

/* ------------------------------ helpers ------------------------------ */
const fmtUsd = (v) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v ?? 0);
const fmtAud = (v) => 'A$' + new Intl.NumberFormat('en-AU', { maximumFractionDigits: 0 }).format(v ?? 0);
const fmtPct = (v) => `${Number(v).toFixed(1)}%`;

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
    blurb: 'A 10-second read of the market: one overall score, the current market "mood" (regime), the live price and the near-term odds.' },
  { id: 'forecasts', label: 'Forecasts', icon: Target,
    blurb: 'Probability-based predictions for the next 24 hours, 7 days and 30 days — never certainties, always odds with a bull/base/bear price range and the maths behind each one.' },
  { id: 'chart', label: 'Chart Intelligence', icon: CandlestickChart,
    blurb: 'Automated technical read of the daily chart: support/resistance zones, trend structure, breakouts, momentum divergences and candlestick patterns — plus historical odds for the current setup.' },
  { id: 'news', label: 'BTC News', icon: Newspaper,
    blurb: 'The news. The meaning. The probable market impact. Each story becomes an AI intelligence card — what happened, why it matters for Bitcoin, likely direction, and an impact score — with links to the original source.' },
  { id: 'cycle', label: 'Cycle & Macro', icon: Globe,
    blurb: 'Where Bitcoin sits in its halving cycle and how capital is rotating across the wider crypto market (BTC dominance).' },
  { id: 'policy', label: 'Policy & Liquidity', icon: Landmark,
    blurb: 'Are global financial conditions becoming more supportive or restrictive for Bitcoin? Central-bank policy, a Global Liquidity Impulse, cross-market correlations, and a regulation tracker that separates proposals from enacted law.' },
  { id: 'analysis', label: 'Quant Analysis', icon: BarChart3,
    blurb: 'The evidence behind the score: each indicator category, the raw feature values the model reads, and which ones matter most.' },
  { id: 'performance', label: 'Performance', icon: Trophy,
    blurb: 'The receipts. Every past prediction graded win/loss, the running accuracy over time, and an honest scoreboard — no cherry-picking.' },
  { id: 'scorecard', label: 'Prediction Ledger', icon: ClipboardList,
    blurb: 'Every forecast is permanently logged before the outcome is known, then graded when it matures. A public scorecard shows directional accuracy, Brier score, error and probability calibration by horizon.' },
  { id: 'trust', label: 'Data Trust', icon: ShieldCheck,
    blurb: 'Provenance for every number: original provider, freshness, latency and confidence. When a live feed goes stale the odds are faded and confidence is reduced automatically.' },
  { id: 'events', label: 'Event Calendar', icon: CalendarClock,
    blurb: 'A unified calendar of macro, derivatives and on-chain events — each with a live countdown, importance and expected volatility, so you can see what could move Bitcoin next.' },
  { id: 'strategy', label: 'Strategy Lab', icon: FlaskConical, soon: true,
    blurb: 'Soon: build no-code rules (e.g. "buy when the score > 70") and backtest them with fees, slippage and drawdown.' },
  { id: 'alerts', label: 'Alerts', icon: Bell,
    blurb: 'A live feed of what just changed and what is coming: regime shifts, liquidity state, chart triggers, cross-market moves and upcoming high-impact policy events.' },
  { id: 'ask', label: 'Ask Quant', icon: MessageCircle,
    blurb: 'Chat with the engine in plain English — "Why did the score fall?", "What is the 7-day outlook?" — and get answers grounded strictly in the live dashboard numbers (powered by Gemini 3 Flash). It will never invent data.' },
];

/* --------------------------- small components ------------------------ */
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
  <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-400">
    <div className="mb-1 flex items-center gap-2 text-slate-300">
      <Info className="h-4 w-4" /><span className="font-semibold">What is this?</span>
    </div>
    {children}
  </div>
);

const AiReview = ({ text }) => (
  <Card className="border-0 bg-gradient-to-br from-violet-500/10 to-slate-900 p-5 ring-1 ring-violet-500/25">
    <div className="mb-2 flex items-center gap-2">
      <Sparkles className="h-4 w-4 text-violet-400" />
      <h3 className="text-sm font-semibold text-violet-200">AI Review</h3>
      <span className="text-[10px] text-slate-500">generated from live model output</span>
    </div>
    <p className="text-sm leading-relaxed text-slate-300">{text}</p>
  </Card>
);

const SectionHead = ({ icon: Icon, title, blurb }) => (
  <div className="space-y-3">
    <div className="flex items-center gap-2">
      <Icon className="h-6 w-6 text-sky-400" />
      <h1 className="text-2xl font-bold tracking-tight text-white">{title}</h1>
    </div>
    <InfoBlock>{blurb}</InfoBlock>
  </div>
);

/* ---------------------------- AI reviews ----------------------------- */
const f24 = (d) => (d.forecasts || []).find((x) => x.horizon === '24H');
const fBy = (d, h) => (d.forecasts || []).find((x) => x.horizon === h);

function reviewOverview(d) {
  const f = f24(d);
  const lean = f ? (f.higher >= f.lower ? 'higher' : 'lower') : 'sideways';
  return `Bitcoin's overall Quant Score is ${d.quant_score}/100 — ${d.quant_label} — and the market is in a "${d.regime.regime}" regime. ${d.regime.description} ${f ? `Over the next 24 hours the model leans ${lean} (${f.higher}% up vs ${f.lower}% down) with ${f.confidence.toLowerCase()} confidence.` : ''} Biggest support: ${d.factors.bullish[0]} Main risk: ${d.factors.risk[0]}`;
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

function DecisionEngineCard({ d }) {
  const dec = d.decision;
  if (!dec) return null;
  return (
    <Card className="border-0 bg-gradient-to-br from-amber-500/[0.07] via-violet-500/[0.08] to-slate-900 p-6 ring-1 ring-violet-500/30 shadow-xl shadow-violet-950/30">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Brain className="h-5 w-5 text-amber-400" />
        <h3 className="text-lg font-bold text-white">Bitcoin Market State</h3>
        <span className="text-[11px] text-slate-500">Unified Decision Engine · reconciles every signal</span>
        {dec.data_trust && <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${dec.data_trust.faded ? 'border-orange-500/30 text-orange-300' : 'border-emerald-500/25 text-emerald-300'}`}>Data trust {dec.data_trust.score}{dec.odds_faded ? ' · odds faded' : ''}</span>}
        <Badge variant="outline" className={`ml-auto border-slate-700 ${alignColor(dec.alignment)}`}>{dec.alignment}</Badge>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-[11px] uppercase tracking-wider text-slate-400">Overall Score</p>
          <p className="mt-1 text-4xl font-black" style={{ color: scoreColor(dec.overall_score) }}>{dec.overall_score}</p>
          <p className="text-sm font-semibold" style={{ color: scoreColor(dec.overall_score) }}>{dec.label}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-[11px] uppercase tracking-wider text-slate-400">Market Regime</p>
          <p className="mt-1 text-lg font-bold leading-tight text-white">{dec.regime}</p>
        </div>
        <div className={`rounded-xl border border-slate-800 bg-slate-950/50 p-4 ring-1 ${riskRing(dec.risk_level)}`}>
          <p className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-slate-400"><ShieldAlert className="h-3 w-3" />Risk Level</p>
          <p className={`mt-1 text-2xl font-black ${riskColor(dec.risk_level)}`}>{dec.risk_level}</p>
          <p className="text-[11px] text-slate-500">risk index {dec.risk_score}/100</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <p className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-slate-400"><Scale className="h-3 w-3" />Signal Alignment</p>
          <p className={`mt-1 text-sm font-bold leading-tight ${alignColor(dec.alignment)}`}>{dec.alignment}</p>
        </div>
      </div>

      {/* component contributions */}
      <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-4">
        {dec.components.map((c) => (
          <div key={c.name} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400">{c.name}</span>
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
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Directional Outlook · 24 hours to 1 year</p>
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

      <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-4">
        <div className="mb-1 flex items-center gap-2 text-slate-300"><Sparkles className="h-4 w-4 text-sky-400" /><span className="text-sm font-semibold">The Bottom Line</span></div>
        <p className="text-sm leading-relaxed text-slate-300">{dec.summary}</p>
      </div>
    </Card>
  );
}

function OverviewSection({ d, ticker }) {
  const f = f24(d);
  const ch = ticker?.change24h ?? d.day_change_pct;
  return (
    <div className="space-y-5">
      <SectionHead icon={LayoutDashboard} title="Overview" blurb={SECTIONS[0].blurb} />
      <DecisionEngineCard d={d} />
      <AiReview text={reviewOverview(d)} />
      <MarketIntelCard d={d} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="flex flex-col items-center border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">Bitcoin Quant Score</p>
          <QuantGauge score={d.quant_score} />
          <p className="mt-3 text-lg font-bold" style={{ color: scoreColor(d.quant_score) }}>{d.quant_label}</p>
        </Card>

        <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
          <div className="mb-2 flex items-center gap-2">
            <Compass className="h-5 w-5 text-sky-400" />
            <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Market Regime</p>
          </div>
          <p className="text-2xl font-bold text-white">{d.regime.regime}</p>
          <p className="mt-2 text-sm leading-relaxed text-slate-400">{d.regime.description}</p>
          <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-400">
            <span className="font-semibold text-slate-200">Model behaviour:</span> {d.regime.behavior}
          </div>
        </Card>

        <div className="space-y-4">
          <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">BTC Live Price</p>
              <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-400">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
                </span>LIVE
              </span>
            </div>
            <p className="mt-1 text-2xl font-bold text-white">{fmtUsd(ticker?.price ?? d.last_close)}</p>
            {ticker?.price_aud && <p className="text-sm font-semibold text-amber-300">≈ {fmtAud(ticker.price_aud)} <span className="text-[10px] font-normal text-slate-500">AUD @ {ticker.aud_rate}</span></p>}
            <p className={`mt-1 flex items-center gap-1 text-sm font-semibold ${ch >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {ch >= 0 ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
              {ch}% (24h){ticker?.source ? ` · ${ticker.source}` : ''}
            </p>
          </Card>
          {f && (
            <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">24-Hour Odds{f.news_link ? ' · news-adjusted' : ''}</p>
              <div className="mt-2 flex items-center gap-3">
                <div className="flex-1">
                  <div className="flex justify-between text-xs"><span className="text-emerald-400">Higher {f.news_link ? f.news_link.higher_adj : f.higher}%</span><span className="text-red-400">{f.news_link ? f.news_link.lower_adj : f.lower}% Lower</span></div>
                  <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-red-500/40">
                    <div className="h-full rounded-full bg-emerald-400" style={{ width: `${f.news_link ? f.news_link.higher_adj : f.higher}%` }} />
                  </div>
                </div>
              </div>
              <p className="mt-2 text-xs text-slate-500">Confidence: <span className="text-slate-300">{f.confidence}</span> · invalid {f.invalidation_dir} {fmtUsd(f.invalidation)}</p>
            </Card>
          )}
        </div>
      </div>

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
  const nl = f.news_link;
  const eff = nl ? nl.higher_adj : f.higher;
  const effLow = nl ? nl.lower_adj : f.lower;
  const bullish = eff >= 50;
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-white">{f.horizon} Forecast</h3>
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
        <div className="flex justify-between"><span className="text-slate-400">Expected range</span><span className="font-mono text-slate-200">{fmtUsd(f.expected_low)} – {fmtUsd(f.expected_high)}</span></div>
        <div className="flex justify-between"><span className="text-slate-400">Confidence</span><span className="font-semibold text-sky-400">{f.confidence} ({f.confidence_pct}%)</span></div>
        <div className="flex justify-between"><span className="text-slate-400">Backtest accuracy</span><span className="text-slate-200">{f.accuracy}%</span></div>
        <div className="flex justify-between"><span className="text-slate-400">Invalidated {f.invalidation_dir}</span><span className="font-mono text-amber-400">{fmtUsd(f.invalidation)}</span></div>
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
      <SectionHead icon={Target} title="Forecasts" blurb={SECTIONS[1].blurb} />
      <AiReview text={reviewForecasts(d)} />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {(d.forecasts || []).map((f) => <ForecastCard key={f.horizon} f={f} />)}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <div className="mb-3 flex items-center gap-2"><TrendingUp className="h-5 w-5 text-emerald-400" /><h3 className="font-semibold text-slate-100">Why it could go up</h3></div>
          <ul className="space-y-2">{d.factors.bullish.map((t, i) => <li key={i} className="flex gap-2 text-sm text-slate-300"><Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />{t}</li>)}</ul>
        </Card>
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <div className="mb-3 flex items-center gap-2"><TrendingDown className="h-5 w-5 text-red-400" /><h3 className="font-semibold text-slate-100">Why it could go down</h3></div>
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
      <AiReview text={reviewAnalysis(d)} />

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
      <SectionHead icon={Trophy} title="Performance" blurb={SECTIONS[3].blurb} />
      <AiReview text={reviewPerformance(d)} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="border-0 bg-gradient-to-br from-sky-500/10 to-slate-900 p-6 ring-1 ring-slate-800">
          <div className="mb-2 flex items-center gap-2"><Trophy className="h-5 w-5 text-amber-400" /><h3 className="font-semibold text-slate-100">AI Scoreboard</h3></div>
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
          <div className="mb-3 flex items-center gap-2"><History className="h-5 w-5 text-slate-400" /><h3 className="font-semibold text-slate-100">Trade Log</h3><span className="text-sm text-slate-500">last {d.trades.length} graded predictions</span></div>
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
        <div className="mb-4"><h3 className="font-semibold text-slate-100">AI Accuracy vs BTC Price</h3><p className="text-sm text-slate-400">30-day rolling accuracy against spot price · {d.first_date} → {d.as_of}</p></div>
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
              <Area yAxisId="left" name="BTC Price" type="monotone" dataKey="btcPrice" stroke="#94a3b8" strokeWidth={1.5} fill="url(#btcFill)" />
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
  if (!c) return <ComingSoonSection section={SECTIONS.find((s) => s.id === 'chart')} />;
  const p = c.predictive;
  const biasColor = (b) => b === 'Bullish' ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' : b === 'Bearish' ? 'text-red-400 border-red-500/30 bg-red-500/10' : 'text-slate-300 border-slate-700 bg-slate-800/40';
  return (
    <div className="space-y-5">
      <SectionHead icon={CandlestickChart} title="Chart Intelligence" blurb={SECTIONS.find((s) => s.id === 'chart').blurb} />
      <AiReview text={reviewChart(d)} />
      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-semibold text-slate-100">Daily Candles · Auto S/R</h3>
          <span className="text-xs text-slate-500">last 90 days · <span className="text-emerald-400">support</span> / <span className="text-red-400">resistance</span></span>
        </div>
        <CandleChart ohlc={c.ohlc} sr={c.sr_levels} />
      </Card>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800 lg:col-span-1">
          <h3 className="mb-3 font-semibold text-slate-100">Predictive Setup</h3>
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
          <h3 className="mb-3 font-semibold text-slate-100">Detected Signals</h3>
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
      <SectionHead icon={Globe} title="Cycle & Macro" blurb={SECTIONS.find((s) => s.id === 'cycle').blurb} />
      <AiReview text={reviewCycle(d)} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {c && (
          <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
            <div className="mb-3 flex items-center gap-2"><Layers className="h-5 w-5 text-amber-400" /><h3 className="font-semibold text-slate-100">Halving Cycle</h3><Badge variant="outline" className="ml-auto border-slate-700 text-amber-400">{c.phase}</Badge></div>
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
            <div className="mb-3 flex items-center gap-2"><Compass className="h-5 w-5 text-sky-400" /><h3 className="font-semibold text-slate-100">BTC Dominance</h3><Badge variant="outline" className="ml-auto border-slate-700 text-sky-400">{dom.direction}</Badge></div>
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
  if (!p) return <ComingSoonSection section={SECTIONS.find((s) => s.id === 'policy')} />;
  return (
    <div className="space-y-5">
      <SectionHead icon={Landmark} title="Policy & Liquidity" blurb={SECTIONS.find((s) => s.id === 'policy').blurb} />
      <AiReview text={reviewPolicy(d)} />

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
        <h3 className="mb-3 font-semibold text-slate-100">Cross-Market Correlations <span className="text-sm font-normal text-slate-500">(rolling, vs BTC)</span></h3>
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
          <h3 className="mb-3 font-semibold text-slate-100">Central-Bank Policy Rates</h3>
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
          <h3 className="mb-3 font-semibold text-slate-100">Policy Event Calendar</h3>
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
        <h3 className="mb-1 font-semibold text-slate-100">Regulation Tracker</h3>
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

function AlertsSection({ d }) {
  const alerts = d.alerts || [];
  const styleFor = (lvl) => lvl === 'danger' ? 'border-red-500/30 bg-red-500/5' : lvl === 'warning' ? 'border-amber-500/30 bg-amber-500/5' : lvl === 'success' ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-slate-800 bg-slate-950/40';
  const dot = (lvl) => lvl === 'danger' ? 'bg-red-400' : lvl === 'warning' ? 'bg-amber-400' : lvl === 'success' ? 'bg-emerald-400' : 'bg-sky-400';
  return (
    <div className="space-y-5">
      <SectionHead icon={Bell} title="Alerts" blurb={SECTIONS.find((s) => s.id === 'alerts').blurb} />
      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <div className="mb-3 flex items-center gap-2"><Bell className="h-5 w-5 text-slate-400" /><h3 className="font-semibold text-slate-100">Live Signal Feed</h3><span className="text-sm text-slate-500">{alerts.length} active</span></div>
        <div className="space-y-2">
          {alerts.map((a, i) => (
            <div key={i} className={`flex items-start gap-3 rounded-lg border p-3 ${styleFor(a.level)}`}>
              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${dot(a.level)}`} />
              <div className="flex-1">
                <div className="flex items-center gap-2"><span className="text-sm font-semibold text-slate-200">{a.type}</span><span className="text-[11px] text-slate-500">{a.ts}</span></div>
                <p className="text-sm text-slate-400">{a.message}</p>
              </div>
            </div>
          ))}
          {alerts.length === 0 && <p className="text-sm text-slate-500">No active alerts right now.</p>}
        </div>
        <p className="mt-4 text-[11px] text-slate-600">In-app feed (no email yet). Add a SendGrid key later to push these as email/push alerts.</p>
      </Card>
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
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded bg-slate-800 px-2 py-0.5 font-medium text-slate-300">{c.source}</span>
        <span className="text-slate-500">credibility {c.credibility}</span>
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
      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
        {th.immediate && <span className="rounded border border-slate-800 px-1.5 py-0.5 text-slate-400">Now: <span className={signalText(th.immediate === 'bullish' ? 'Bullish' : th.immediate === 'bearish' ? 'Bearish' : 'Neutral')}>{th.immediate}</span></span>}
        {th.seven_day && <span className="rounded border border-slate-800 px-1.5 py-0.5 text-slate-400">7d: {th.seven_day}</span>}
        {th.long_term && <span className="rounded border border-slate-800 px-1.5 py-0.5 text-slate-400">Long: {th.long_term}</span>}
        {(ai.categories || []).slice(0, 3).map((cat, i) => <span key={i} className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-400">{String(cat).replace(/_/g, ' ')}</span>)}
        {ai.confidence != null && <span className="ml-auto text-slate-500">confidence {Math.round((ai.confidence || 0) * 100)}%</span>}
      </div>
    </Card>
  );
}

function NewsSection({ news, status, onRefresh, refreshing }) {
  const [filter, setFilter] = React.useState('all');
  if (status !== 'ready' || !news) {
    return (
      <div className="space-y-5">
        <SectionHead icon={Newspaper} title="BTC News" blurb={SECTIONS.find((s) => s.id === 'news').blurb} />
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
      <SectionHead icon={Newspaper} title="BTC News" blurb={SECTIONS.find((s) => s.id === 'news').blurb} />
      <Card className="border-0 bg-gradient-to-br from-violet-500/10 to-slate-900 p-6 ring-1 ring-violet-500/25">
        <div className="mb-3 flex items-center gap-2"><Sparkles className="h-5 w-5 text-violet-400" /><h3 className="font-semibold text-slate-100">Daily AI Briefing</h3><span className="ml-auto text-[11px] text-slate-500">{news.model}</span></div>
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

function Stat({ label, value, sub, color }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <p className="text-[11px] uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-1 text-3xl font-black" style={color ? { color } : undefined}>{value}</p>
      {sub && <p className="text-[11px] text-slate-500">{sub}</p>}
    </div>
  );
}

function ScorecardSection({ d }) {
  const pl = d.prediction_ledger;
  if (!pl) return <ComingSoonSection section={SECTIONS.find((s) => s.id === 'scorecard')} />;
  const o = pl.overall;
  const accCol = o.accuracy == null ? undefined : scoreColor(o.accuracy);
  return (
    <div className="space-y-5">
      <SectionHead icon={ClipboardList} title="Prediction Ledger" blurb={SECTIONS.find((s) => s.id === 'scorecard').blurb} />
      <div className="rounded-xl border border-sky-500/20 bg-sky-500/[0.06] p-4 text-sm text-slate-300">
        <span className="font-semibold text-sky-300">Accountability by design.</span> Every forecast is written to the ledger the moment it is issued — before the outcome exists — then graded automatically when it matures. Model <span className="font-mono text-slate-200">{pl.model_version}</span> · <span className="text-slate-200">{pl.total_logged}</span> forecasts logged (<span className="text-slate-200">{pl.live_logged}</span> live-forward + <span className="text-slate-200">{pl.backtested}</span> walk-forward backtest).
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Directional Accuracy" value={o.accuracy == null ? '—' : `${o.accuracy}%`} sub={`${o.n} graded`} color={accCol} />
        <Stat label="Brier Score" value={o.brier == null ? '—' : o.brier} sub="lower is better (0 = perfect)" />
        <Stat label="Mean Abs. Error" value={o.mae_pct == null ? '—' : `${o.mae_pct}%`} sub="base-case price vs actual" />
        <Stat label="Range Hit Rate" value={o.range_hit_pct == null ? '—' : `${o.range_hit_pct}%`} sub="actual inside base range" />
      </div>

      {Object.keys(pl.by_horizon).length > 0 && (
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <h3 className="mb-3 text-sm font-semibold text-white">Results by Forecast Horizon</h3>
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
          <h3 className="mb-1 text-sm font-semibold text-white">Probability Calibration</h3>
          <p className="mb-3 text-xs text-slate-500">When the model says a bucket of odds, how often did price actually go up? Closer bars = better-calibrated.</p>
          <div className="space-y-3">
            {pl.calibration.map((c) => (
              <div key={c.bucket}>
                <div className="flex justify-between text-xs text-slate-400"><span>Predicted {c.bucket} <span className="text-slate-600">({c.n})</span></span><span>realised up {c.realised_up}%</span></div>
                <div className="mt-1 flex gap-1">
                  <div className="h-2 flex-1 rounded-full bg-slate-800"><div className="h-full rounded-full bg-sky-500" style={{ width: `${c.avg_pred}%` }} /></div>
                  <div className="h-2 flex-1 rounded-full bg-slate-800"><div className="h-full rounded-full bg-emerald-500" style={{ width: `${c.realised_up}%` }} /></div>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-4 text-[11px] text-slate-500"><span className="flex items-center gap-1"><span className="h-2 w-3 rounded bg-sky-500" />avg predicted</span><span className="flex items-center gap-1"><span className="h-2 w-3 rounded bg-emerald-500" />actual up-rate</span></div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white"><CalendarClock className="h-4 w-4 text-amber-400" />Open Forecasts (awaiting outcome)</h3>
          {pl.pending.length === 0 ? <p className="text-sm text-slate-500">No open forecasts yet — they appear here the moment each run is issued.</p> : (
            <div className="space-y-2">
              {pl.pending.map((p, i) => (
                <div key={i} className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-2.5 text-sm">
                  <span className="w-10 font-bold text-slate-200">{p.horizon}</span>
                  <span className={`font-semibold ${p.direction === 'UP' ? 'text-emerald-400' : 'text-red-400'}`}>{p.direction} {p.prob_higher}%</span>
                  <span className="text-slate-500">→ {p.target_date}</span>
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
    </div>
  );
}

/* ------------------------- Data Trust Layer -------------------------- */
function DataTrustSection({ d }) {
  const h = d.data_health;
  if (!h) return <ComingSoonSection section={SECTIONS.find((s) => s.id === 'trust')} />;
  const col = h.score >= 90 ? '#34d399' : h.score >= 75 ? '#a3e635' : h.score >= 55 ? '#fbbf24' : '#f87171';
  return (
    <div className="space-y-5">
      <SectionHead icon={ShieldCheck} title="Data Trust" blurb={SECTIONS.find((s) => s.id === 'trust').blurb} />
      <Card className={`border-0 bg-gradient-to-br from-slate-900 to-slate-950 p-6 ring-1 ${h.faded ? 'ring-orange-500/40' : 'ring-emerald-500/25'}`}>
        <div className="flex flex-wrap items-center gap-6">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-slate-400">Overall Data Trust</p>
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
  if (!ec) return <ComingSoonSection section={SECTIONS.find((s) => s.id === 'events')} />;
  const nx = ec.next_high_impact;
  return (
    <div className="space-y-5">
      <SectionHead icon={CalendarClock} title="Event Calendar" blurb={SECTIONS.find((s) => s.id === 'events').blurb} />
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
  const [sessionId] = React.useState(() => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2)));
  const [messages, setMessages] = React.useState([]);
  const [input, setInput] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const endRef = React.useRef(null);

  React.useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading]);

  const suggestions = [
    'Summarise the current Bitcoin market state in plain English.',
    'Why is the quant score where it is right now?',
    "What's the 7-day outlook and how confident is it?",
    'How is the latest news affecting the forecast?',
    'What are the biggest risks right now?',
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
        body: JSON.stringify({ session_id: sessionId, message: msg }),
      });
      const j = await r.json();
      setMessages((m) => [...m, { role: 'assistant', text: j.text || 'Sorry, I could not answer that just now.' }]);
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', text: 'Network error — please try again.' }]);
    } finally { setLoading(false); }
  };

  return (
    <div className="space-y-5">
      <SectionHead icon={MessageCircle} title="Ask Quant" blurb={SECTIONS.find((s) => s.id === 'ask').blurb} />
      <Card className="flex h-[560px] flex-col overflow-hidden border-0 bg-slate-900 p-0 ring-1 ring-slate-800">
        <div className="flex items-center gap-2 border-b border-slate-800 px-5 py-3">
          <div className="rounded-lg bg-gradient-to-br from-sky-500 to-violet-600 p-1.5"><Brain className="h-4 w-4 text-white" /></div>
          <div><p className="text-sm font-semibold text-white">Quant · AI Analyst</p><p className="text-[10px] text-slate-500">Grounded in live dashboard data · Gemini 3 Flash</p></div>
          <span className="ml-auto flex items-center gap-1 text-[10px] font-bold text-emerald-400"><span className="h-2 w-2 rounded-full bg-emerald-400" />LIVE</span>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <div className="rounded-full bg-slate-800 p-4"><MessageCircle className="h-7 w-7 text-sky-400" /></div>
              <div>
                <p className="font-semibold text-slate-200">Ask me anything about the current market</p>
                <p className="mt-1 max-w-sm text-xs text-slate-500">I only use the live numbers on this dashboard — score, regime, forecasts, news, policy and cycle. I won't invent data.</p>
              </div>
              <div className="flex max-w-lg flex-wrap justify-center gap-2">
                {suggestions.map((s, i) => (
                  <button key={i} onClick={() => send(s)} className="rounded-full border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs text-slate-300 hover:border-sky-500/40 hover:text-sky-300">{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${m.role === 'user' ? 'bg-sky-500/15 text-sky-50 ring-1 ring-sky-500/25' : 'bg-slate-950/60 text-slate-200 ring-1 ring-slate-800'}`}>{m.text}</div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="flex items-center gap-1.5 rounded-2xl bg-slate-950/60 px-4 py-3 ring-1 ring-slate-800">
                <span className="h-2 w-2 animate-bounce rounded-full bg-sky-400" style={{ animationDelay: '0ms' }} />
                <span className="h-2 w-2 animate-bounce rounded-full bg-sky-400" style={{ animationDelay: '150ms' }} />
                <span className="h-2 w-2 animate-bounce rounded-full bg-sky-400" style={{ animationDelay: '300ms' }} />
              </div>
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
              placeholder="Ask about the score, forecasts, news impact, risks…"
              className="max-h-32 flex-1 resize-none rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:border-sky-500/50 focus:outline-none"
            />
            <Button onClick={() => send()} disabled={loading || !input.trim()} className="gap-1.5 bg-sky-500 hover:bg-sky-400"><Send className="h-4 w-4" />Send</Button>
          </div>
          <p className="mt-2 text-center text-[10px] text-slate-600">Educational research assistant · not financial advice · grounded in live data but can still be imperfect.</p>
        </div>
      </Card>
    </div>
  );
}

/* ----------------------------- page ---------------------------------- */
// Module-level caches survive a Fast-Refresh / remount so the dashboard never
// flickers back to the full-screen loader once data has been fetched once.
let __dashCache = null;
let __tickerCache = null;
let __newsCache = null;
export default function DashboardPage() {
  const [data, setData] = useState(__dashCache);
  const [status, setStatus] = useState(__dashCache ? 'ready' : 'loading');
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [ticker, setTicker] = useState(__tickerCache);
  const [active, setActive] = useState('overview');
  const [news, setNews] = useState(__newsCache);
  const [newsStatus, setNewsStatus] = useState(__newsCache ? 'ready' : 'loading');
  const [newsRefreshing, setNewsRefreshing] = useState(false);

  const loadNews = useCallback(async () => {
    try {
      const r = await fetch('/api/v1/news', { cache: 'no-store' });
      const j = await r.json();
      if (j.status === 'ready') { __newsCache = j; setNews(j); setNewsStatus('ready'); setNewsRefreshing(false); }
      else setNewsStatus(j.status || 'computing');
    } catch (e) { setNewsStatus('error'); }
  }, []);

  useEffect(() => {
    loadNews();
    const id = setInterval(() => { setNewsStatus((s) => { if (s !== 'ready') loadNews(); return s; }); }, 5000);
    return () => clearInterval(id);
  }, [loadNews]);

  const handleNewsRefresh = async () => {
    setNewsRefreshing(true);
    await fetch('/api/v1/news/refresh', { method: 'POST' });
    const id = setInterval(loadNews, 5000);
    setTimeout(() => clearInterval(id), 70000);
  };

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/dashboard', { cache: 'no-store' });
      const json = await res.json();
      if (json.status === 'ready') { __dashCache = json; setData(json); setStatus('ready'); setRefreshing(false); }
      else if (json.status === 'error') { setError(json.error || 'Unknown error'); setStatus('error'); }
      else setStatus('computing');
    } catch (e) { setError(String(e)); setStatus('error'); }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(() => { setStatus((s) => { if (s !== 'ready') load(); return s; }); }, 4000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    let alive = true;
    const loadTicker = async () => {
      try { const r = await fetch('/api/v1/ticker', { cache: 'no-store' }); const j = await r.json(); if (alive && j && j.price) { __tickerCache = j; setTicker(j); } } catch (e) { /* noop */ }
    };
    loadTicker();
    const t = setInterval(loadTicker, 10000);
    const dref = setInterval(() => load(), 60000);
    return () => { alive = false; clearInterval(t); clearInterval(dref); };
  }, [load]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetch('/api/v1/refresh', { method: 'POST' });
    const id = setInterval(load, 4000);
    setTimeout(() => clearInterval(id), 90000);
  };

  if (!data && (status === 'loading' || status === 'computing')) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-slate-950 px-6">
        <img src="/btciq-logo.png" alt="BTCIQ" className="h-14 w-auto object-contain" />
        <div className="relative"><div className="h-16 w-16 animate-spin rounded-full border-4 border-slate-800 border-t-sky-400" /><Cpu className="absolute inset-0 m-auto h-6 w-6 text-sky-400" /></div>
        <div className="text-center"><h2 className="text-lg font-semibold text-slate-100">Building Bitcoin intelligence…</h2><p className="mt-1 text-sm text-slate-400">BTCIQ · powered by BitCentAI · decision engine · news-linked forecasts · backtests</p></div>
      </main>
    );
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
  const activeSection = SECTIONS.find((s) => s.id === active);
  const renderSection = () => {
    if (active === 'overview') return <OverviewSection d={d} ticker={ticker} />;
    if (active === 'forecasts') return <ForecastsSection d={d} />;
    if (active === 'chart') return <ChartSection d={d} />;
    if (active === 'news') return <NewsSection news={news} status={newsStatus} onRefresh={handleNewsRefresh} refreshing={newsRefreshing} />;
    if (active === 'cycle') return <CycleSection d={d} />;
    if (active === 'policy') return <PolicySection d={d} />;
    if (active === 'analysis') return <AnalysisSection d={d} />;
    if (active === 'performance') return <PerformanceSection d={d} />;
    if (active === 'scorecard') return <ScorecardSection d={d} />;
    if (active === 'trust') return <DataTrustSection d={d} />;
    if (active === 'events') return <EventsSection d={d} />;
    if (active === 'alerts') return <AlertsSection d={d} />;
    if (active === 'ask') return <AskQuantSection d={d} />;
    return <ComingSoonSection section={activeSection} />;
  };

  return (
    <div className="relative min-h-screen bg-slate-950 text-slate-100">
      <div aria-hidden className="pointer-events-none fixed inset-0 bg-[radial-gradient(55rem_38rem_at_-8%_-12%,rgba(247,147,26,0.10),transparent_58%),radial-gradient(52rem_40rem_at_112%_6%,rgba(109,94,246,0.14),transparent_55%)]" />
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
            {SECTIONS.map((s) => {
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
        </aside>

        {/* Main */}
        <div className="min-w-0 flex-1">
          {/* Top bar */}
          <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-slate-800 bg-slate-950/80 px-4 py-3 backdrop-blur md:px-8">
            <div className="flex items-center gap-2 md:hidden"><img src="/btciq-logo.png" alt="BTCIQ" className="h-6 w-auto object-contain" /></div>
            <div className="hidden items-center gap-2 md:flex">
              <span className="flex items-center gap-1 text-xs font-bold text-emerald-400">
                <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" /><span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" /></span>LIVE
              </span>
              <span className="text-lg font-bold text-white">{fmtUsd(ticker?.price ?? d.last_close)}</span>
              {ticker?.price_aud && <span className="rounded-md bg-amber-500/10 px-1.5 py-0.5 text-xs font-semibold text-amber-300 ring-1 ring-amber-500/20">≈ {fmtAud(ticker.price_aud)}</span>}
              <span className={`text-sm font-semibold ${(ticker?.change24h ?? d.day_change_pct) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{ticker?.change24h ?? d.day_change_pct}%</span>
            </div>
            <Button onClick={handleRefresh} disabled={refreshing} size="sm" className="gap-2 bg-gradient-to-r from-sky-500 to-violet-600 text-white shadow-lg shadow-violet-500/20 hover:from-sky-400 hover:to-violet-500">
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />{refreshing ? 'Retraining' : 'Retrain'}
            </Button>
          </div>

          {/* Mobile nav */}
          <div className="flex gap-1 overflow-x-auto border-b border-slate-800 px-3 py-2 md:hidden">
            {SECTIONS.map((s) => (
              <button key={s.id} onClick={() => setActive(s.id)} className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-xs ${active === s.id ? 'bg-sky-500/15 font-semibold text-sky-300' : 'text-slate-400'}`}>{s.label}</button>
            ))}
          </div>

          <main className="mx-auto max-w-6xl px-4 py-6 md:px-8">{renderSection()}</main>
          <footer className="pb-8 text-center text-xs text-slate-600">BTCIQ · powered by BitCentAI · educational research tool, not financial advice · real data via {d.data_source}</footer>
        </div>
      </div>
    </div>
  );
}
