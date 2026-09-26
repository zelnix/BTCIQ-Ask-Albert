'use client';
// App Diagnosis & Checkup — plain-English health screen. Runs the deterministic
// backend checkup, shows outcome + likely cause + confidence + ONE safe action,
// with a collapsible technical-details view. Reads state; never changes trading data.
import React from 'react';
import { API_BASE, getPid } from '../lib/api';
import {
  Loader2, CheckCircle2, AlertTriangle, XCircle, Stethoscope, ChevronDown, RefreshCw, Info, ShieldCheck,
} from 'lucide-react';

const outcomeTone = (o) => ({
  healthy: { fg: 'text-emerald-300', bg: 'bg-emerald-500/10', ring: 'ring-emerald-500/30', Icon: CheckCircle2 },
  degraded: { fg: 'text-amber-300', bg: 'bg-amber-500/10', ring: 'ring-amber-500/30', Icon: AlertTriangle },
  failing: { fg: 'text-rose-300', bg: 'bg-rose-500/10', ring: 'ring-rose-500/30', Icon: XCircle },
}[o] || { fg: 'text-slate-300', bg: 'bg-slate-500/10', ring: 'ring-slate-500/25', Icon: Info });

const resultDot = { PASS: 'bg-emerald-400', WARN: 'bg-amber-400', FAIL: 'bg-rose-400', SKIP: 'bg-slate-600' };
const confLabel = { CONFIRMED: 'Confirmed', LIKELY: 'Likely', POSSIBLE: 'Possible', UNKNOWN: 'Unclear' };

export default function DiagnosticsCheckup() {
  const [d, setD] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const [showTech, setShowTech] = React.useState(false);
  const [verify, setVerify] = React.useState(null);

  const runCheckup = async () => {
    setBusy(true); setVerify(null); setShowTech(false);
    try {
      const client = { app_version: '1.0.0', platform: 'web', build_number: 'web' };
      const r = await fetch(`${API_BASE}/v1/albert/diagnostics/checkups`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client, pid: getPid(), include_optional_notifications: false }),
      });
      const j = await r.json();
      setD(j && j.status === 'ready' ? j : null);
    } catch (e) { setD(null); }
    setBusy(false);
  };

  const doVerify = async () => {
    if (!d) return;
    setBusy(true);
    try {
      const r = await fetch(`${API_BASE}/v1/albert/diagnostics/runs/${d.run_id}/verify`, { method: 'POST' });
      const j = await r.json();
      setVerify(j);
      if (j && j.summary) setD((prev) => ({ ...prev, summary: j.summary, run_id: j.newRunId || prev.run_id }));
    } catch (e) { /* noop */ }
    setBusy(false);
  };

  const tone = d ? outcomeTone(d.summary?.outcome) : outcomeTone();
  const Tone = tone.Icon;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="flex items-center gap-2 text-xl font-bold text-white"><Stethoscope className="h-5 w-5 text-sky-300" />App Checkup</h2>
        <p className="mt-0.5 text-[12px] text-slate-400">Albert can check the parts of Ask Albert needed for the app to work correctly.</p>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="flex items-center gap-1.5 text-[12px] text-slate-400"><ShieldCheck className="h-4 w-4 text-emerald-400" />No passwords or sensitive credentials are collected — this only reads service health.</p>
          <button onClick={runCheckup} disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg bg-sky-500/20 px-4 py-2 text-[13px] font-semibold text-sky-200 hover:bg-sky-500/30 disabled:opacity-60">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {d ? 'Run again' : 'Run App Checkup'}
          </button>
        </div>
        {d && <p className="mt-2 text-[10px] text-slate-500">Last checkup: {new Date(d.completed_at).toLocaleString()} · run {d.run_id}</p>}
      </div>

      {d && (
        <>
          <div className={`rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 to-slate-950 p-4 ring-1 ${tone.ring}`}>
            <div className="flex items-start gap-3">
              <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${tone.bg} ${tone.fg}`}><Tone className="h-6 w-6" /></span>
              <div className="flex-1">
                <p className={`text-lg font-bold ${tone.fg}`}>{d.summary?.title}</p>
                <p className="mt-0.5 text-[10px] uppercase tracking-wide text-slate-500">Confidence: {confLabel[d.summary?.confidence] || d.summary?.confidence}</p>
              </div>
            </div>
            <div className="mt-3 space-y-2">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">What happened</p>
                <p className="text-[13px] text-slate-200">{d.summary?.plain_meaning}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Likely or confirmed cause</p>
                <p className="text-[13px] text-slate-200">{d.diagnosis?.category?.replace(/_/g, ' ')} · code {d.diagnosis?.public_code}</p>
              </div>
            </div>
            {d.recommended_action && d.recommended_action.action_id !== 'none' && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button onClick={d.recommended_action.action_id === 'retry' ? runCheckup : undefined} disabled={busy}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-3.5 py-1.5 text-[12px] font-semibold text-slate-900 hover:bg-white disabled:opacity-60">
                  {d.recommended_action.label}
                </button>
                {d.verification?.available && (
                  <button onClick={doVerify} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-[12px] font-semibold text-slate-300 hover:text-white">
                    {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}Check again
                  </button>
                )}
              </div>
            )}
            {verify && (
              <p className={`mt-2 text-[12px] font-semibold ${verify.outcome === 'fixed' ? 'text-emerald-300' : verify.outcome === 'still_failing' ? 'text-rose-300' : 'text-amber-300'}`}>
                Verification: {verify.outcome === 'fixed' ? 'Resolved ✓' : verify.outcome === 'still_failing' ? 'Still failing' : 'Unable to verify'}
              </p>
            )}
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">What Albert checked</p>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {(d.technical_details?.checks || []).map((c, i) => (
                <div key={i} className="flex items-center gap-2 text-[11.5px]">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${resultDot[c.result] || 'bg-slate-600'}`} />
                  <span className="text-slate-300">{c.check_id}</span>
                  <span className="ml-auto text-[10px] text-slate-500">{c.result} · {c.duration_ms}ms</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
            <button onClick={() => setShowTech((s) => !s)} className="flex w-full items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Technical details</span>
              <ChevronDown className={`h-4 w-4 text-slate-500 transition-transform ${showTech ? 'rotate-180' : ''}`} />
            </button>
            {showTech && (
              <div className="mt-3 space-y-1 text-[11px] text-slate-400">
                <p>Run ID: <span className="font-mono text-slate-300">{d.run_id}</span></p>
                <p>Timestamp: {d.completed_at}</p>
                <p>Ruleset: {d.diagnosis?.ruleset_version}</p>
                <p>Redactions: {d.technical_details?.redaction_count}</p>
                <p>Evidence refs: {(d.diagnosis?.evidence_refs || []).join(', ') || 'none'}</p>
                <div className="mt-2 space-y-0.5">
                  {(d.technical_details?.checks || []).map((c, i) => (
                    <p key={i} className="font-mono text-[10px] text-slate-500">{c.check_id} → {c.result} · {c.evidence_code}{c.note ? ` · ${c.note}` : ''}</p>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
