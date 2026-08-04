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
  Sparkles, Info, Lock, Compass, CandlestickChart, Layers, Landmark, Globe,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

/* ------------------------------ helpers ------------------------------ */
const fmtUsd = (v) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v ?? 0);
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
  { id: 'cycle', label: 'Cycle & Macro', icon: Globe,
    blurb: 'Where Bitcoin sits in its halving cycle and how capital is rotating across the wider crypto market (BTC dominance).' },
  { id: 'analysis', label: 'Quant Analysis', icon: BarChart3,
    blurb: 'The evidence behind the score: each indicator category, the raw feature values the model reads, and which ones matter most.' },
  { id: 'performance', label: 'Performance', icon: Trophy,
    blurb: 'The receipts. Every past prediction graded win/loss, the running accuracy over time, and an honest scoreboard — no cherry-picking.' },
  { id: 'strategy', label: 'Strategy Lab', icon: FlaskConical, soon: true,
    blurb: 'Soon: build no-code rules (e.g. "buy when the score > 70") and backtest them with fees, slippage and drawdown.' },
  { id: 'alerts', label: 'Alerts', icon: Bell, soon: true,
    blurb: 'Soon: get notified when the regime flips, probabilities cross a threshold, or price hits a key level.' },
  { id: 'ask', label: 'Ask Quant', icon: MessageCircle, soon: true,
    blurb: 'Soon: chat with the engine — "Why did the score fall?" — with plain-English answers grounded in the real numbers.' },
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
function OverviewSection({ d, ticker }) {
  const f = f24(d);
  const ch = ticker?.change24h ?? d.day_change_pct;
  return (
    <div className="space-y-5">
      <SectionHead icon={LayoutDashboard} title="Overview" blurb={SECTIONS[0].blurb} />
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
            <p className={`mt-1 flex items-center gap-1 text-sm font-semibold ${ch >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {ch >= 0 ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
              {ch}% (24h){ticker?.source ? ` · ${ticker.source}` : ''}
            </p>
          </Card>
          {f && (
            <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">24-Hour Odds</p>
              <div className="mt-2 flex items-center gap-3">
                <div className="flex-1">
                  <div className="flex justify-between text-xs"><span className="text-emerald-400">Higher {f.higher}%</span><span className="text-red-400">{f.lower}% Lower</span></div>
                  <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-red-500/40">
                    <div className="h-full rounded-full bg-emerald-400" style={{ width: `${f.higher}%` }} />
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

function ForecastCard({ f }) {
  const bullish = f.higher >= f.lower;
  return (
    <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-white">{f.horizon} Forecast</h3>
        <Badge variant="outline" className={`border-slate-700 ${bullish ? 'text-emerald-400' : 'text-red-400'}`}>{bullish ? 'Leans Up' : 'Leans Down'}</Badge>
      </div>
      <div className="mt-3">
        <div className="flex justify-between text-sm font-semibold"><span className="text-emerald-400">Higher {f.higher}%</span><span className="text-red-400">{f.lower}% Lower</span></div>
        <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-red-500/40">
          <div className="h-full rounded-full bg-emerald-400" style={{ width: `${f.higher}%` }} />
        </div>
      </div>
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

/* ----------------------------- page ---------------------------------- */
export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [ticker, setTicker] = useState(null);
  const [active, setActive] = useState('overview');

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/dashboard', { cache: 'no-store' });
      const json = await res.json();
      if (json.status === 'ready') { setData(json); setStatus('ready'); setRefreshing(false); }
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
      try { const r = await fetch('/api/v1/ticker', { cache: 'no-store' }); const j = await r.json(); if (alive && j && j.price) setTicker(j); } catch (e) { /* noop */ }
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

  if (status === 'loading' || status === 'computing') {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-slate-950 px-6">
        <div className="relative"><div className="h-16 w-16 animate-spin rounded-full border-4 border-slate-800 border-t-sky-400" /><Cpu className="absolute inset-0 m-auto h-6 w-6 text-sky-400" /></div>
        <div className="text-center"><h2 className="text-lg font-semibold text-slate-100">Building Bitcoin intelligence…</h2><p className="mt-1 text-sm text-slate-400">Real market data · score · regime · multi-horizon forecasts · backtests</p></div>
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
  const activeSection = SECTIONS.find((s) => s.id === active);
  const renderSection = () => {
    if (active === 'overview') return <OverviewSection d={d} ticker={ticker} />;
    if (active === 'forecasts') return <ForecastsSection d={d} />;
    if (active === 'chart') return <ChartSection d={d} />;
    if (active === 'cycle') return <CycleSection d={d} />;
    if (active === 'analysis') return <AnalysisSection d={d} />;
    if (active === 'performance') return <PerformanceSection d={d} />;
    return <ComingSoonSection section={activeSection} />;
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="flex">
        {/* Sidebar */}
        <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-slate-800 bg-slate-900/50 p-4 md:flex">
          <div className="mb-6 flex items-center gap-2 px-2">
            <div className="rounded-xl bg-gradient-to-br from-sky-500 to-violet-600 p-2"><Activity className="h-5 w-5 text-white" /></div>
            <div><p className="text-sm font-bold leading-tight text-white">Bitcoin Quant</p><p className="text-[10px] text-slate-500">Explainable Intelligence</p></div>
          </div>
          <nav className="flex-1 space-y-1">
            {SECTIONS.map((s) => {
              const Icon = s.icon;
              const on = active === s.id;
              return (
                <button key={s.id} onClick={() => setActive(s.id)}
                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${on ? 'bg-sky-500/15 font-semibold text-sky-300' : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'}`}>
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
            <div className="flex items-center gap-2 md:hidden"><Activity className="h-5 w-5 text-sky-400" /><span className="font-bold">Bitcoin Quant</span></div>
            <div className="hidden items-center gap-2 md:flex">
              <span className="flex items-center gap-1 text-xs font-bold text-emerald-400">
                <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" /><span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" /></span>LIVE
              </span>
              <span className="text-lg font-bold text-white">{fmtUsd(ticker?.price ?? d.last_close)}</span>
              <span className={`text-sm font-semibold ${(ticker?.change24h ?? d.day_change_pct) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{ticker?.change24h ?? d.day_change_pct}%</span>
            </div>
            <Button onClick={handleRefresh} disabled={refreshing} size="sm" className="gap-2 bg-slate-800 text-slate-100 hover:bg-slate-700">
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
          <footer className="pb-8 text-center text-xs text-slate-600">Educational research tool · not financial advice · real data via {d.data_source}</footer>
        </div>
      </div>
    </div>
  );
}
