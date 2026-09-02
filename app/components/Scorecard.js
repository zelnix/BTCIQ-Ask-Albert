'use client';

import React, { useState, useEffect } from 'react';
import { CalendarClock, Check, ClipboardList, Info, X, ShieldCheck, Activity, AlertTriangle } from 'lucide-react';
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ReferenceLine, Cell, LineChart, Line } from 'recharts';
import { Card } from '@/components/ui/card';
import { API_BASE } from '../lib/api';
import { fmtUsd, scoreColor, countdown } from '../lib/format';
import { sec } from '../lib/sections';
import { SectionHead, AiReview, InfoTip, ComingSoonSection } from './shared';

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

function QuantValidationPanel() {
  const [v, setV] = useState(null);
  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/v1/validation`, { cache: 'no-store' })
      .then((r) => r.json()).then((j) => { if (alive && j && j.status === 'ready') setV(j); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);
  if (!v) return null;
  const b = v.benchmarks || {};
  const pct = (x) => (x == null ? '—' : `${Math.round(x * 100)}%`);
  const roll = (v.rolling_brier_history || []).map((y, i) => ({ i, y }));
  const Pass = ({ ok }) => ok
    ? <span className="rounded-full border border-emerald-500/40 px-1.5 py-0.5 text-[9px] font-bold text-emerald-300">PASS</span>
    : <span className="rounded-full border border-amber-500/40 px-1.5 py-0.5 text-[9px] font-bold text-amber-300">WATCH</span>;
  return (
    <Card className="border-0 bg-gradient-to-br from-sky-500/[0.06] to-slate-900 p-5 ring-1 ring-sky-500/25">
      <h3 className="mb-1 flex items-center gap-1 text-sm font-semibold text-white"><ShieldCheck className="h-4 w-4 text-sky-400" />Quant-Grade Validation<InfoTip below text="Purged & embargoed walk-forward validation (removes look-ahead leakage from the forward-looking triple-barrier labels). PSR/DSR correct the Sharpe ratio for fat tails and data-snooping across model trials." /></h3>
      <p className="mb-3 text-xs text-slate-500">{v.n_trades} purged out-of-sample trades · {v.horizon_bars}-bar triple-barrier holding.</p>
      {(v.coverage_alerts || []).length > 0 && (
        <div className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-[12px] text-amber-200">
          <span className="font-semibold">Coverage alert:</span> {v.coverage_alerts.map((a) => `${a.horizon} band at ${a.coverage}%`).join(', ')} — below the 80% floor, so {v.coverage_alerts.length > 1 ? 'these corridors are' : 'this corridor is'} running too tight and will auto-widen next run.
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><div className="flex items-center justify-between"><p className="text-[10px] uppercase text-slate-500">Brier</p><Pass ok={b.brier_pass} /></div><p className="mt-1 text-2xl font-black" style={{ color: b.brier_pass ? '#34d399' : '#f87171' }}>{v.brier_score}</p><p className="text-[10px] text-slate-600">target &lt;0.20</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><div className="flex items-center justify-between"><p className="text-[10px] uppercase text-slate-500">PSR</p><Pass ok={b.psr_pass} /></div><p className="mt-1 text-2xl font-black" style={{ color: b.psr_pass ? '#34d399' : '#fbbf24' }}>{pct(v.probabilistic_sharpe_ratio)}</p><p className="text-[10px] text-slate-600">target &gt;95%</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><div className="flex items-center justify-between"><p className="text-[10px] uppercase text-slate-500">DSR</p><Pass ok={b.dsr_pass} /></div><p className="mt-1 text-2xl font-black" style={{ color: b.dsr_pass ? '#34d399' : '#fbbf24' }}>{pct(v.deflated_sharpe_ratio)}</p><p className="text-[10px] text-slate-600">target &gt;90%</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><p className="text-[10px] uppercase text-slate-500">Ann. Sharpe</p><p className="mt-1 text-2xl font-black text-slate-200">{v.annualized_sharpe}</p><p className="text-[10px] text-slate-600">max DD {v.max_drawdown_pct}%</p></div>
      </div>
      {roll.length > 3 && (
        <div className="mt-4">
          <p className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Rolling Brier Decay<InfoTip text="60-trade rolling Brier score over time. A flat or falling line means the model's edge is holding; a rising line above 0.24 signals decay and would trigger a down-weight/alert." /><span className={`ml-2 rounded px-1.5 py-0.5 text-[9px] font-bold ${b.brier_decay_pass ? 'text-emerald-300' : 'text-amber-300'}`}>slope {v.rolling_brier_slope}</span></p>
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={roll} margin={{ top: 5, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="#1e293b" vertical={false} />
              <YAxis domain={['auto', 'auto']} tick={{ fill: '#64748b', fontSize: 10 }} width={40} />
              <ReferenceLine y={0.24} stroke="#f87171" strokeDasharray="4 4" />
              <ReferenceLine y={0.25} stroke="#475569" strokeDasharray="2 2" />
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }} formatter={(y) => [y, 'Brier']} />
              <Line type="monotone" dataKey="y" stroke="#38bdf8" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-1 text-[10px] text-slate-500">Red line = 0.24 decay alert threshold · grey = 0.25 coin-flip baseline.</p>
        </div>
      )}
      {(v.coverage_history_by_horizon || v.coverage_history) && (() => {
        const byh = v.coverage_history_by_horizon || {};
        const hzKeys = ['24H', '7D', '30D'].filter((k) => (byh[k] || []).length > 2);
        const colors = { '24H': '#38bdf8', '7D': '#a78bfa', '30D': '#f59e0b' };
        let data = [];
        if (hzKeys.length) {
          const wk = {};
          hzKeys.forEach((k) => (byh[k] || []).forEach((p) => { wk[p.week] = wk[p.week] || { week: p.week }; wk[p.week][k] = p.coverage; }));
          data = Object.values(wk).sort((a, b) => a.week - b.week);
        } else if ((v.coverage_history || []).length > 2) {
          data = v.coverage_history; hzKeys.push('coverage'); colors.coverage = '#a78bfa';
        }
        if (data.length <= 2) return null;
        return (
          <div className="mt-4">
            <p className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Corridor Coverage by Horizon<InfoTip text="How often the actual price landed inside each horizon's 90% conformal corridor, by week. Should hover near the 90% target line — a line drifting below means that band is running too tight." /></p>
            <ResponsiveContainer width="100%" height={140}>
              <LineChart data={data} margin={{ top: 5, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#1e293b" vertical={false} />
                <XAxis dataKey="week" tick={{ fill: '#64748b', fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 10 }} width={36} unit="%" />
                <ReferenceLine y={v.coverage_target || 90} stroke="#34d399" strokeDasharray="4 4" />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }} formatter={(y, n) => [`${y}%`, n]} />
                {hzKeys.map((k) => <Line key={k} type="monotone" dataKey={k} name={k === 'coverage' ? 'coverage' : k} stroke={colors[k]} strokeWidth={2} dot={{ r: 2 }} connectNulls />)}
              </LineChart>
            </ResponsiveContainer>
            <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-slate-500">
              {hzKeys.filter((k) => k !== 'coverage').map((k) => <span key={k} className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ background: colors[k] }} />{k}</span>)}
              <span className="flex items-center gap-1"><span className="h-0.5 w-4" style={{ borderTop: '2px dashed #34d399' }} />{v.coverage_target || 90}% target</span>
            </div>
          </div>
        );
      })()}
    </Card>
  );
}


function DriftMonitorPanel() {
  const [v, setV] = React.useState(null);
  React.useEffect(() => {
    fetch(`${API_BASE}/v1/drift`, { cache: 'no-store' })
      .then((r) => r.json()).then(setV).catch(() => {});
  }, []);
  if (!v || !Array.isArray(v.per_feature) || !v.per_feature.length) return null;

  const breaker = !!v.circuit_breaker;
  const level = v.confidence_level || 'Normal';
  const levelStyle = breaker
    ? 'text-red-300 border-red-500/30 bg-red-500/10'
    : level === 'Guarded'
      ? 'text-amber-300 border-amber-500/30 bg-amber-500/10'
      : 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10';
  const ood = v.ood || {};
  const feats = v.per_feature || [];
  const statusColor = (s) => (s === 'drift' ? '#f87171' : s === 'watch' ? '#fbbf24' : '#34d399');

  return (
    <Card className="border-0 bg-slate-900 p-4 ring-1 ring-slate-800">
      <h3 className="mb-1 flex flex-wrap items-center gap-2 text-sm font-semibold text-white">
        <Activity className="h-4 w-4 text-sky-400" />Feature-Drift Circuit Breaker
        <InfoTip below text="Watches whether today's live inputs sit outside the distribution the model trained on (robust z-scores + a multivariate Mahalanobis gate) and whether the core data feeds are complete. If inputs are out-of-distribution or feeds drop below 95%, it downgrades model confidence to Low and falls back to a conservative rule-based trend model. PSI & KS per-feature are shown as diagnostics." />
        <span className={`ml-auto rounded-full border px-2 py-0.5 text-[10px] font-bold ${levelStyle}`}>
          {breaker ? 'BREAKER TRIPPED' : `Confidence: ${level}`}
        </span>
      </h3>

      {breaker && (
        <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-[11px] leading-snug text-red-200">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            <span className="font-semibold">Model reverted to rule-based trend following.</span>{' '}
            {(v.reasons || []).join(' ')} Fallback call: <span className="font-semibold">{v.fallback_signal?.signal}</span> ({v.fallback_signal?.confidence}%).
          </span>
        </div>
      )}

      <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
          <p className="text-[10px] uppercase text-slate-500">Model mode</p>
          <p className="mt-1 text-lg font-black" style={{ color: breaker ? '#f87171' : '#34d399' }}>{v.model_mode === 'rule_based' ? 'Rule-based' : 'ML'}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
          <p className="text-[10px] uppercase text-slate-500">Data completeness</p>
          <p className="mt-1 text-lg font-black" style={{ color: (v.data_completeness_pct ?? 100) < (v.completeness_min || 95) ? '#f87171' : '#34d399' }}>{v.data_completeness_pct}%</p>
          <p className="text-[10px] text-slate-600">min {v.completeness_min}%</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
          <p className="text-[10px] uppercase text-slate-500">Anomaly (Mahalanobis)</p>
          <p className="mt-1 text-lg font-black" style={{ color: ood.mahalanobis != null && ood.maha_threshold != null && ood.mahalanobis > ood.maha_threshold ? '#f87171' : '#34d399' }}>{ood.mahalanobis ?? '—'}</p>
          <p className="text-[10px] text-slate-600">gate {ood.maha_threshold ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
          <p className="text-[10px] uppercase text-slate-500">Effective signal</p>
          <p className="mt-1 text-lg font-black text-slate-100">{v.effective_signal || '—'}</p>
          <p className="text-[10px] text-slate-600">ML said {v.ml_signal || '—'}</p>
        </div>
      </div>

      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Per-feature drift (recent {v.recent_window}d vs prior {v.reference_window}d)</p>
      <div className="overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full text-left text-[11px]">
          <thead className="bg-slate-950/60 text-slate-500">
            <tr>
              <th className="px-2 py-1 font-medium">Feature</th>
              <th className="px-2 py-1 font-medium">PSI</th>
              <th className="px-2 py-1 font-medium">KS</th>
              <th className="px-2 py-1 font-medium">Live z</th>
              <th className="px-2 py-1 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {feats.map((f) => (
              <tr key={f.feature} className="border-t border-slate-800/70 text-slate-300">
                <td className="px-2 py-1">{f.label}</td>
                <td className="px-2 py-1 tabular-nums">{f.psi}</td>
                <td className="px-2 py-1 tabular-nums">{f.ks_stat}{f.ks_significant ? '*' : ''}</td>
                <td className="px-2 py-1 tabular-nums">{ood.robust_z?.[f.feature] ?? '—'}</td>
                <td className="px-2 py-1"><span className="rounded px-1.5 py-0.5 text-[10px] font-bold" style={{ color: statusColor(f.status) }}>{f.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[10px] text-slate-600">PSI &gt; 0.25 with a significant KS test (*) marks a shifted distribution. The breaker itself trips only when the live vector is out-of-distribution (extreme z / Mahalanobis) or feeds fall below {v.completeness_min}% — so normal market evolution won't needlessly disable the model.</p>
    </Card>
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
    fetch(`${API_BASE}/v1/scorecard`, { cache: 'no-store' })
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
                    <img src="/albert.png" alt="Albert" className="h-11 w-11 rounded-full object-cover ring-2 ring-sky-500/40" />
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

      <QuantValidationPanel />

      <DriftMonitorPanel />

      {pl.reliability && pl.reliability.curve?.length > 0 && (
        <Card className="border-0 bg-gradient-to-br from-violet-500/[0.06] to-slate-900 p-5 ring-1 ring-violet-500/25">
          <h3 className="mb-1 flex items-center gap-1 text-sm font-semibold text-white">Model Reliability<InfoTip below text="How trustworthy the stated probabilities are. Brier skill compares the model to a random 50/50 coin flip (above 0 = better than a coin flip). ECE is the average gap between what the model predicted and what actually happened, in percentage points (lower = better calibrated)." /></h3>
          <p className="mb-3 text-xs text-slate-500">Graded on {pl.reliability.n} resolved forecasts.</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Brier Score" value={pl.reliability.brier ?? '—'} sub="0 = perfect · 0.25 = coin flip" color={pl.reliability.brier != null && pl.reliability.brier <= 0.25 ? '#34d399' : '#f87171'} />
            <Stat label="Brier Skill" value={pl.reliability.brier_skill == null ? '—' : (pl.reliability.brier_skill > 0 ? '+' : '') + pl.reliability.brier_skill} sub="vs a 50/50 coin flip" color={pl.reliability.brier_skill != null && pl.reliability.brier_skill > 0 ? '#34d399' : '#f87171'} />
            <Stat label="Calibration Error" value={pl.reliability.ece == null ? '—' : pl.reliability.ece + 'pt'} sub="mean pred vs actual gap" color={pl.reliability.ece != null && pl.reliability.ece < 6 ? '#34d399' : pl.reliability.ece < 12 ? '#fbbf24' : '#f87171'} />
            <Stat label="Verdict" value={pl.reliability.grade || '—'} sub="overall calibration" color={pl.reliability.grade === 'Well calibrated' ? '#34d399' : pl.reliability.grade === 'Fairly calibrated' ? '#fbbf24' : '#f87171'} />
          </div>
        </Card>
      )}

      {(pl.reliability?.curve?.length > 0 || pl.calibration?.length > 0) && (
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <h3 className="mb-1 flex items-center gap-1 text-sm font-semibold text-white">Calibration Curve<InfoTip below text="Checks whether the model's stated odds match reality — e.g. of all the times it said '70% up', did BTC actually rise about 70% of the time?" /></h3>
          <p className="mb-3 text-xs text-slate-500">Each dot is a bucket of forecasts: X = what the model predicted, Y = how often price actually rose. The closer to the dashed line, the better calibrated. Bubble size = number of forecasts.</p>
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart margin={{ top: 10, right: 20, bottom: 24, left: 0 }}>
              <CartesianGrid stroke="#1e293b" />
              <XAxis type="number" dataKey="avg_pred" domain={[0, 100]} name="Predicted" unit="%" tick={{ fill: '#94a3b8', fontSize: 11 }} label={{ value: 'Predicted probability of higher (%)', position: 'insideBottom', offset: -12, fill: '#64748b', fontSize: 11 }} />
              <YAxis type="number" dataKey="realised_up" domain={[0, 100]} name="Actual" unit="%" tick={{ fill: '#94a3b8', fontSize: 11 }} label={{ value: 'Actual up-rate (%)', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11 }} />
              <ZAxis type="number" dataKey="n" range={[80, 500]} name="samples" />
              <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 100, y: 100 }]} stroke="#64748b" strokeDasharray="5 5" ifOverflow="extendDomain" />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }} formatter={(v, n) => [`${v}${n === 'samples' ? '' : '%'}`, n]} />
              <Scatter data={pl.reliability?.curve?.length > 0 ? pl.reliability.curve : pl.calibration}>
                {(pl.reliability?.curve?.length > 0 ? pl.reliability.curve : pl.calibration).map((c, i) => {
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

export default ScorecardSection;
