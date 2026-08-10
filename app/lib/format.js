// Pure formatting + color helpers shared across the dashboard (no React state).

export const fmtUsd = (v) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v ?? 0);
export const fmtAud = (v) => 'A$' + new Intl.NumberFormat('en-AU', { maximumFractionDigits: 0 }).format(v ?? 0);
export const fmtPct = (v) => `${Number(v).toFixed(1)}%`;

export const CAT_COLORS = {
  Trend: 'text-sky-400 bg-sky-500/10 border-sky-500/30',
  Momentum: 'text-violet-400 bg-violet-500/10 border-violet-500/30',
  Volatility: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  Volume: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
};
export const BAR_COLORS = ['#38bdf8', '#a78bfa', '#fbbf24', '#34d399', '#f472b6', '#60a5fa', '#f87171', '#4ade80'];

// Mobile-friendly touch target (>=44px) for chart timeframe/window buttons; compact on >= sm screens.
export const TF_TOUCH = 'min-h-[44px] min-w-[44px] inline-flex items-center justify-center sm:min-h-0 sm:min-w-0';

export const scoreColor = (s) =>
  s >= 60 ? '#34d399' : s >= 55 ? '#a3e635' : s > 45 ? '#fbbf24' : s > 40 ? '#fb923c' : '#f87171';
export const signalText = (w) =>
  w === 'Bullish' || w === 'UP' ? 'text-emerald-400'
    : w === 'Bearish' || w === 'DOWN' ? 'text-red-400' : 'text-slate-300';

// ---- shared color / date helpers (centralised during Stage 3 refactor) ----
export const sigHex = (s) => s === 'Bullish' ? '#34d399' : s === 'Bearish' ? '#f87171' : '#94a3b8';
export const sigColor = (s) => s === 'Bullish' ? 'text-emerald-400' : s === 'Bearish' ? 'text-red-400' : 'text-slate-400';
export const shortDate = (iso) => { try { return new Date(iso + (iso.length <= 10 ? 'T00:00:00Z' : '')).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' }); } catch { return iso; } };
export const riskColor = (lvl) => ({
  Low: 'text-emerald-400', Moderate: 'text-lime-400', Elevated: 'text-amber-400',
  High: 'text-orange-400', Extreme: 'text-red-400',
}[lvl] || 'text-slate-300');

// ---- countdown (centralised) ----
export function countdown(dateStr) {
  const t = new Date(dateStr + 'T13:30:00Z').getTime() - Date.now();
  if (t <= 0) return 'now';
  const d = Math.floor(t / 86400000); const h = Math.floor((t % 86400000) / 3600000);
  return d > 0 ? `${d}d ${h}h` : `${h}h`;
}

// ---- forecast lookups + news direction colours (centralised) ----
export const f24 = (d) => (d.forecasts || []).find((x) => x.horizon === '24H');
export const fBy = (d, h) => (d.forecasts || []).find((x) => x.horizon === h);
export const DIR_COLOR = {
  bullish: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10',
  bearish: 'text-red-400 border-red-500/30 bg-red-500/10',
  mixed: 'text-amber-400 border-amber-500/30 bg-amber-500/10',
  neutral: 'text-slate-400 border-slate-700 bg-slate-800/40',
};

// ---- correlation color helper (for cross-market correlations) ----
export const corrColor = (corr) => {
  if (corr == null) return 'text-slate-500';
  const val = parseFloat(corr);
  if (val >= 0.5) return 'text-emerald-400';
  if (val >= 0.2) return 'text-lime-400';
  if (val > -0.2) return 'text-slate-400';
  if (val > -0.5) return 'text-orange-400';
  return 'text-red-400';
};
