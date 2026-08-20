'use client';

import React from 'react';
import { CalendarClock, Check, ClipboardList, Info, X } from 'lucide-react';
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ReferenceLine, Cell } from 'recharts';
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
