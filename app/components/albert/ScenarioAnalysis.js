'use client';

import React, { useCallback, useEffect } from 'react';
import { X, FlaskConical, ShieldCheck, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import ScenarioChart from './ScenarioChart';
import { EvidenceButton, Limitations, ratioPct, signedPct, money, shortDate } from './common';

function Row({ label, value, hint }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-slate-800/70 py-1.5 last:border-0">
      <div className="min-w-0">
        <p className="text-[12px] text-slate-400">{label}</p>
        {hint ? <p className="text-[10.5px] leading-tight text-slate-600">{hint}</p> : null}
      </div>
      <p className="shrink-0 text-[12.5px] font-semibold text-white">{value}</p>
    </div>
  );
}

/**
 * "Expand analysis" opens OVER Home rather than navigating away, so the user's place in
 * the two streams — scroll position, selected asset, selected horizon, open sections — is
 * still exactly there when they close it.
 */
export default function ScenarioAnalysis({
  outlook, asset, assets, horizon, onAsset, onHorizon, onEvidence, onAsk, onClose, leadership,
}) {
  const onKey = useCallback((e) => { if (e.key === 'Escape') onClose(); }, [onClose]);
  useEffect(() => {
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onKey]);

  const band = outlook?.band;
  const sample = outlook?.sample;
  const snap = band?.snapshotId;
  const available = !!band?.available;

  return (
    <div className="fixed inset-0 z-[60] overflow-y-auto bg-slate-950/85 backdrop-blur-sm p-2 sm:p-6"
      role="dialog" aria-modal="true" aria-label="Scenario analysis">
      <div className="mx-auto w-full max-w-[1400px] rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl">
        <div className="flex items-center gap-3 border-b border-slate-800 px-4 py-3">
          <FlaskConical className="h-4 w-4 shrink-0 text-sky-400" />
          <div className="min-w-0">
            <p className="truncate text-sm font-bold text-white">Scenario analysis · {outlook?.assetId}</p>
            <p className="truncate text-[11px] text-slate-500">
              Historical scenario range, the matched periods behind it, and the provider’s own walk-forward report card
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close analysis"
            className="ml-auto rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-4 sm:p-5">
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3 sm:p-4">
            <ScenarioChart embedded outlook={outlook} asset={asset} assets={assets}
              horizon={horizon} onAsset={onAsset} onHorizon={onHorizon}
              onEvidence={onEvidence} onAsk={onAsk} chartHeight={420} histCount={90}
              leadership={leadership} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3.5">
              <p className="mb-2 flex items-center gap-1.5 text-[12px] font-bold uppercase tracking-wider text-slate-300">
                Validation
                <EvidenceButton snapshotId={snap} onEvidence={onEvidence} label="snapshot" />
              </p>
              {available ? (
                <div>
                  <Row label="Band coverage" value={ratioPct(band.coverageRate)}
                    hint={`target ${ratioPct(band.coverageTarget, 0)}`} />
                  <Row label="Chronological checks" value={band.evaluationPoints}
                    hint="walk-forward, no look-ahead" />
                  <Row label="Median absolute error" value={`${band.medianAbsErrorPct}%`} />
                  <Row label="No-change baseline error" value={`${band.baselineMedianAbsErrorPct}%`}
                    hint="what saying nothing would have scored" />
                  <Row label="Skill vs no change" value={(band.skillVsNoChange ?? 0).toFixed(3)}
                    hint="at or near zero means no skill" />
                  <Row label="Evaluated period"
                    value={`${band.firstEvaluatedAt || '—'} → ${band.lastEvaluatedAt || '—'}`} />
                  {band.regimeCoverage ? (
                    <Row label="Regime coverage"
                      value={`${band.regimeCoverage.up} up · ${band.regimeCoverage.down} down · ${band.regimeCoverage.flat} flat`} />
                  ) : null}
                  <p className="mt-2 rounded-lg border border-amber-500/25 bg-amber-500/[0.06] p-2 text-[11.5px] leading-relaxed text-amber-100/90">
                    {band.validationHeadline}
                  </p>
                  <p className="mt-1.5 text-[11px] text-slate-500">
                    Required label: <span className="font-semibold text-slate-300">{band.labelRequirement}</span>
                  </p>
                </div>
              ) : (
                <p className="text-[12.5px] leading-relaxed text-slate-400">
                  No validated band is published, so no validation figures are shown.
                  {band?.reasonText ? ` ${band.reasonText}` : ''}
                </p>
              )}
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3.5">
              <p className="mb-2 text-[12px] font-bold uppercase tracking-wider text-slate-300">Matched periods</p>
              {sample ? (
                <div>
                  <Row label="Matched days" value={sample.sampleSize} />
                  <Row label="Distinct episodes" value={sample.independentEpisodes}
                    hint="adjacent days share a forward window, so this is the effective sample" />
                  <Row label="Candidate pool" value={sample.candidatePool}
                    hint="days with a known forward outcome" />
                  {sample.similarity ? (
                    <Row label="Similarity"
                      value={`best ${sample.similarity.best} · median ${sample.similarity.median}`} />
                  ) : null}
                  {sample.percentiles ? (
                    <Row label="Percentiles used"
                      value={`${sample.percentiles.bearish}th / ${sample.percentiles.median}th / ${sample.percentiles.bullish}th`} />
                  ) : null}
                  {(sample.matchedDates || []).length ? (
                    <div className="mt-2">
                      <p className="mb-1 text-[11px] text-slate-500">Closest matched days</p>
                      <div className="flex flex-wrap gap-1.5">
                        {sample.matchedDates.map((d) => (
                          <span key={d} className="rounded-md border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[10.5px] font-mono text-slate-300">{d}</span>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {(sample.features || []).length ? (
                    <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                      Conditions compared on: {sample.features.join(', ')} — all strictly trailing.
                    </p>
                  ) : null}
                  <Limitations className="mt-2" items={sample.sampleLimitations} />
                </div>
              ) : (
                <p className="text-[12.5px] text-slate-400">No matched sample is available.</p>
              )}
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3.5">
              <p className="mb-2 text-[12px] font-bold uppercase tracking-wider text-slate-300">Anchor &amp; scope</p>
              {outlook?.baseline ? (
                <div>
                  <Row label="Anchor price" value={money(outlook.baseline.price)} />
                  <Row label="Anchor candle" value={shortDate(outlook.baseline.observedAt)}
                    hint="last CLOSED candle; the forming candle is trimmed" />
                  {available ? (
                    <>
                      <Row label="Lower edge" value={`${money(band.lowerPrice)} (${signedPct(band.lowerPct)})`} />
                      <Row label="Upper edge" value={`${money(band.upperPrice)} (${signedPct(band.upperPct)})`} />
                    </>
                  ) : null}
                  <Row label="Market leadership"
                    value={String(leadership || outlook.phase?.assessed || '—').replace(/_/g, ' ')}
                    hint="observed assessment · read-only · not a scenario control" />
                  <Row label="Horizon" value={`${outlook.horizonDays} days`} />
                </div>
              ) : null}
              {outlook?.phase?.note ? (
                <p className="mt-2 text-[11px] leading-relaxed text-slate-500">{outlook.phase.note}</p>
              ) : null}
              {(outlook?.scenarios || []).length ? (
                <div className="mt-2.5">
                  <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">What would invalidate this</p>
                  <ul className="space-y-1 text-[11.5px] leading-relaxed text-slate-400">
                    {(outlook.scenarios[0].invalidation || []).map((t, i) => (
                      <li key={i} className="flex gap-1.5"><span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-slate-600" /><span>{t}</span></li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 border-t border-slate-800 pt-3">
            <Button size="sm" onClick={onClose}
              className="h-8 gap-1.5 bg-slate-100 px-3 text-[12px] font-semibold text-slate-900 hover:bg-white">
              <ArrowLeft className="h-3.5 w-3.5" />Back to Albert home
            </Button>
            <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
              Read-only preview · it cannot create a proposal, an order or a strategy change
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
