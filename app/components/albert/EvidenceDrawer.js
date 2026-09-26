'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { X, ShieldCheck, Loader2, AlertTriangle, MessageCircle, Lock, Globe } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { API_BASE } from '../../lib/api';
import { timeAgo } from './common';

const HIDE_KEYS = new Set(['note', 'guardrail', 'accounting']);

function prettyKey(k) {
  return String(k)
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_.]/g, ' ')
    .replace(/^./, (c) => c.toUpperCase());
}

function Scalar({ value }) {
  if (value === null || value === undefined || value === '') return <span className="text-slate-500">—</span>;
  if (typeof value === 'boolean') {
    return <span className={value ? 'text-emerald-300' : 'text-amber-300'}>{value ? 'yes' : 'no'}</span>;
  }
  return <span className="break-words text-slate-200">{String(value)}</span>;
}

function Node({ label, value, depth = 0 }) {
  if (value === null || value === undefined) {
    return (
      <div className="flex items-start justify-between gap-3 py-1">
        <span className="shrink-0 text-[11px] text-slate-500">{prettyKey(label)}</span>
        <span className="text-[12px] text-slate-500">—</span>
      </div>
    );
  }
  if (Array.isArray(value)) {
    if (!value.length) {
      return (
        <div className="flex items-start justify-between gap-3 py-1">
          <span className="shrink-0 text-[11px] text-slate-500">{prettyKey(label)}</span>
          <span className="text-[12px] text-slate-500">none</span>
        </div>
      );
    }
    const scalars = value.every((v) => v === null || typeof v !== 'object');
    return (
      <div className="py-1">
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{prettyKey(label)}</p>
        {scalars ? (
          <p className="text-[12px] leading-relaxed text-slate-200">{value.map((v) => String(v)).join(' · ')}</p>
        ) : (
          <div className="space-y-2">
            {value.slice(0, 12).map((v, i) => (
              <div key={i} className="rounded-lg border border-slate-800 bg-slate-950/50 p-2">
                <Node label={`#${i + 1}`} value={v} depth={depth + 1} />
              </div>
            ))}
            {value.length > 12 ? <p className="text-[11px] text-slate-500">…and {value.length - 12} more</p> : null}
          </div>
        )}
      </div>
    );
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value).filter(([k]) => !HIDE_KEYS.has(k));
    return (
      <div className={depth === 0 ? 'space-y-1' : 'space-y-0.5'}>
        {depth > 0 && label && !String(label).startsWith('#') ? (
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{prettyKey(label)}</p>
        ) : null}
        {entries.map(([k, v]) => <Node key={k} label={k} value={v} depth={depth + 1} />)}
      </div>
    );
  }
  return (
    <div className="flex items-start justify-between gap-3 py-1">
      <span className="shrink-0 text-[11px] text-slate-500">{prettyKey(label)}</span>
      <span className="min-w-0 text-right text-[12px] font-medium"><Scalar value={value} /></span>
    </div>
  );
}

/**
 * Evidence opens IN PLACE, over whatever the user was reading. Nothing about the page
 * behind it is unmounted or reset, so closing the panel returns the user to exactly the
 * scroll position, selection and expanded state they left.
 */
export default function EvidenceDrawer({ snapshotId, onClose, onAsk }) {
  const [state, setState] = useState('loading');
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (!snapshotId) return undefined;
    let alive = true;
    setState('loading'); setData(null); setErr('');
    fetch(`${API_BASE}/v1/albert/evidence/${encodeURIComponent(snapshotId)}`,
      { credentials: 'include', cache: 'no-store' })
      .then(async (r) => {
        if (!alive) return;
        if (r.status === 404) { setErr('That evidence record is not available to your account.'); setState('error'); return; }
        if (r.status === 401 || r.status === 403) { setErr('Please sign in to open evidence.'); setState('error'); return; }
        if (!r.ok) { setErr('Evidence could not be loaded.'); setState('error'); return; }
        const j = await r.json();
        if (!alive) return;
        setData(j); setState('ready');
      })
      .catch(() => { if (alive) { setErr('Network error loading evidence.'); setState('error'); } });
    return () => { alive = false; };
  }, [snapshotId]);

  const onKey = useCallback((e) => { if (e.key === 'Escape') onClose(); }, [onClose]);
  useEffect(() => {
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onKey]);

  if (!snapshotId) return null;
  const payload = data?.payload || {};
  const limitations = payload.limitations || payload.sampleLimitations || null;

  return (
    <div className="fixed inset-0 z-[70] flex justify-end" role="dialog" aria-modal="true"
      aria-label="Evidence">
      <button type="button" aria-label="Close evidence" onClick={onClose}
        className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm" />
      <div className="relative flex h-full w-full max-w-full flex-col border-l border-slate-800 bg-slate-900 shadow-2xl sm:w-[540px]">
        <div className="flex items-start gap-3 border-b border-slate-800 px-4 py-3">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-sky-400" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-bold text-white">{data?.title || 'Evidence'}</p>
            <p className="truncate text-[11px] text-slate-500">
              {data?.kind ? `${data.kind} · ` : ''}{snapshotId}
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {state === 'loading' && (
            <p className="flex items-center gap-2 text-[13px] text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin" />Opening the exact snapshot…
            </p>
          )}
          {state === 'error' && (
            <p className="flex items-start gap-2 text-[13px] text-amber-300">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{err}
            </p>
          )}
          {state === 'ready' && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <span className="inline-flex items-center gap-1 rounded-full bg-slate-950/70 px-2 py-0.5 font-semibold text-slate-300 ring-1 ring-slate-700">
                  {data.scope === 'OWNER' ? <Lock className="h-3 w-3" /> : <Globe className="h-3 w-3" />}
                  {data.scope === 'OWNER' ? 'Your record' : 'Market record'}
                </span>
                {data.asOf ? <span className="text-slate-500">Source time {String(data.asOf).replace('T', ' ').slice(0, 16)}</span> : null}
                {data.createdAt ? <span className="text-slate-600">captured {timeAgo(data.createdAt)}</span> : null}
              </div>

              {payload.statement ? (
                <p className="rounded-xl border border-sky-500/25 bg-sky-500/[0.06] p-3 text-[13px] font-semibold leading-relaxed text-sky-100">
                  {payload.statement}
                </p>
              ) : null}
              {payload.hypothesis ? (
                <p className="rounded-xl border border-violet-500/25 bg-violet-500/[0.06] p-3 text-[13px] leading-relaxed text-violet-100">
                  {payload.hypothesis}
                </p>
              ) : null}
              {payload.reply ? (
                <div className="rounded-xl border border-slate-700 bg-slate-950/60 p-3">
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Question</p>
                  <p className="mb-2 text-[13px] text-slate-300">{payload.question}</p>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Albert’s answer</p>
                  <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-slate-200">{payload.reply}</p>
                </div>
              ) : null}

              <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">The record</p>
                <Node label="" value={payload} />
              </div>

              {Array.isArray(limitations) && limitations.length ? (
                <div className="rounded-xl border border-amber-500/25 bg-amber-500/[0.05] p-3">
                  <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-amber-300">What this cannot tell you</p>
                  <ul className="space-y-1 text-[12px] leading-relaxed text-amber-100/80">
                    {limitations.map((l, i) => <li key={i}>• {l}</li>)}
                  </ul>
                </div>
              ) : null}

              {payload.note ? <p className="text-[11px] leading-relaxed text-slate-500">{payload.note}</p> : null}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-slate-800 px-4 py-3">
          <Button size="sm" onClick={onClose} className="h-8 bg-slate-100 px-3 text-[12px] font-semibold text-slate-900 hover:bg-white">
            Close and go back
          </Button>
          {onAsk ? (
            <Button size="sm" variant="outline" onClick={() => onAsk(snapshotId, data)}
              className="h-8 gap-1.5 border-slate-700 bg-transparent px-3 text-[12px] text-slate-200 hover:bg-slate-800">
              <MessageCircle className="h-3.5 w-3.5" />Ask Albert about this
            </Button>
          ) : null}
          <p className="ml-auto text-[10px] text-slate-600">Read-only · paper trading only</p>
        </div>
      </div>
    </div>
  );
}
