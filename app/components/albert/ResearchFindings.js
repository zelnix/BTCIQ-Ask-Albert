'use client';

import React, { useState } from 'react';
import {
  Lightbulb, ShieldAlert, Microscope, Eye, HelpCircle, ChevronDown, MessageCircle,
  CheckCircle2, XCircle, Clock,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { EvidenceButton, KnowledgeBadge, Limitations, StatusBadge, timeAgo } from './common';

const PRIORITY = {
  AVOID_FOR_NOW: { label: 'Avoid for now', icon: ShieldAlert, cls: 'border-red-500/40 bg-red-500/[0.06]', text: 'text-red-300' },
  CONSIDER_PAPER_TEST: { label: 'Consider a paper test', icon: Microscope, cls: 'border-violet-500/40 bg-violet-500/[0.06]', text: 'text-violet-300' },
  INVESTIGATE: { label: 'Investigate', icon: Lightbulb, cls: 'border-sky-500/40 bg-sky-500/[0.06]', text: 'text-sky-300' },
  WATCH: { label: 'Watch', icon: Eye, cls: 'border-slate-700 bg-slate-950/50', text: 'text-slate-300' },
  INSUFFICIENT_EVIDENCE: { label: 'Insufficient evidence', icon: HelpCircle, cls: 'border-slate-800 bg-slate-950/40', text: 'text-slate-400' },
};

const OUTCOME = {
  CONFIRMED: { icon: CheckCircle2, cls: 'text-emerald-400', label: 'Confirmed' },
  INVALIDATED: { icon: XCircle, cls: 'text-red-400', label: 'Invalidated' },
  EXPIRED_UNRESOLVED: { icon: Clock, cls: 'text-slate-400', label: 'Expired unresolved' },
};

function Finding({ f, onEvidence, onAsk }) {
  const [open, setOpen] = useState(false);
  const p = PRIORITY[f.priority] || PRIORITY.WATCH;
  const Icon = p.icon;
  const hasHypothesis = f.status !== 'NO_HYPOTHESIS';
  return (
    <div className={`rounded-xl border p-3 ${p.cls}`}>
      <div className="flex items-start gap-2.5">
        <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${p.text}`} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={`text-[10px] font-bold uppercase tracking-wider ${p.text}`}>{f.priorityLabel || p.label}</span>
            <KnowledgeBadge kind={f.knowledgeType} />
            {hasHypothesis ? (
              <span className="text-[10px] text-slate-500">open {timeAgo(f.openedAt)}</span>
            ) : (
              <span className="text-[10px] text-slate-500">no falsifiable condition — not scored</span>
            )}
          </div>
          <p className="mt-1 text-[13.5px] font-semibold leading-snug text-white">{f.title}</p>
          <p className="mt-1 max-w-[95ch] text-[12.5px] leading-relaxed text-slate-300">{f.hypothesis}</p>

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
            <EvidenceButton snapshotId={f.snapshotId} onEvidence={onEvidence} label="Supporting snapshot" />
            {hasHypothesis ? (
              <button type="button" onClick={() => setOpen((o) => !o)}
                className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400 hover:text-slate-200">
                <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
                How this resolves
              </button>
            ) : null}
            {onAsk ? (
              <button type="button" onClick={() => onAsk(f)}
                className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400 hover:text-sky-300">
                <MessageCircle className="h-3.5 w-3.5" />Ask Albert
              </button>
            ) : null}
          </div>

          {open ? (
            <div className="mt-2 space-y-1.5 rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
              <p className="text-[12px] text-slate-300">
                <span className="font-semibold text-emerald-300">Confirmed if:</span> {f.confirmIf}
              </p>
              <p className="text-[12px] text-slate-300">
                <span className="font-semibold text-red-300">Invalidated if:</span> {f.invalidateIf}
              </p>
              <p className="text-[11.5px] text-slate-500">
                Measure <span className="font-mono">{f.measure?.name}</span> · opened at{' '}
                {String(f.measure?.openValue)} · latest {String(f.measure?.latestValue)} ·{' '}
                {f.observationCount} observation{f.observationCount === 1 ? '' : 's'} · resolves by{' '}
                {String(f.resolveBy || '').slice(0, 10)}
              </p>
              <Limitations items={f.limitations} />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default function ResearchFindings({ research, onEvidence, onAsk }) {
  const [showHistory, setShowHistory] = useState(false);
  const findings = research?.findings || [];
  const resolved = research?.recentlyResolved || [];
  const sc = research?.scorecard;
  return (
    <Card className="border-0 bg-slate-900 p-4 ring-1 ring-slate-800 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-2 text-sm font-bold text-white">
          <Lightbulb className="h-4 w-4 text-amber-400" />Research findings
        </h3>
        <StatusBadge status={research?.status} />
        {sc ? (
          <span className="ml-auto text-[11px] text-slate-500">
            {sc.open} open · {sc.confirmed} confirmed · {sc.invalidated} invalidated
            {sc.expiredUnresolved ? ` · ${sc.expiredUnresolved} expired` : ''}
          </span>
        ) : null}
      </div>

      {findings.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-[13px] text-slate-400">
          No research finding is open right now. {research?.reasonCode ? `(${research.reasonCode})` : ''}
        </p>
      ) : (
        <div className="space-y-2.5">
          {findings.map((f) => (
            <Finding key={f.findingId || f.key} f={f} onEvidence={onEvidence} onAsk={onAsk} />
          ))}
        </div>
      )}

      {resolved.length ? (
        <div className="mt-3">
          <button type="button" onClick={() => setShowHistory((s) => !s)}
            className="inline-flex items-center gap-1 text-[11.5px] font-semibold text-slate-400 hover:text-slate-200">
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showHistory ? 'rotate-180' : ''}`} />
            Outcome history ({resolved.length})
          </button>
          {showHistory ? (
            <div className="mt-2 space-y-1.5">
              {resolved.map((r) => {
                const o = OUTCOME[r.status] || OUTCOME.EXPIRED_UNRESOLVED;
                const OIcon = o.icon;
                return (
                  <div key={r.findingId} className="flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-950/50 p-2.5">
                    <OIcon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${o.cls}`} />
                    <div className="min-w-0 flex-1">
                      <p className="text-[12.5px] font-semibold text-slate-200">
                        <span className={o.cls}>{o.label}</span> · {r.title}
                      </p>
                      <p className="text-[11.5px] leading-relaxed text-slate-500">{r.outcome?.text}</p>
                      <p className="mt-0.5 text-[10.5px] text-slate-600">
                        held {r.outcome?.heldDays} days · resolved {timeAgo(r.outcome?.at)}
                      </p>
                    </div>
                    <EvidenceButton snapshotId={r.snapshotId} onEvidence={onEvidence} label="Snapshot" />
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}

      {sc?.note ? <p className="mt-2.5 text-[11px] leading-relaxed text-slate-500">{sc.note}</p> : null}
      <Limitations className="mt-2" items={research?.limitations} />
    </Card>
  );
}
