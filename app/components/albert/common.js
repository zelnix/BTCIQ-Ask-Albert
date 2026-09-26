'use client';

import React, { useEffect, useRef, useState } from 'react';
import { ShieldCheck, Eye, FileText, Cpu, MessageCircle, HelpCircle, Beaker } from 'lucide-react';

/* ----------------------------- formatting ----------------------------- */
export const num = (v) => (v === null || v === undefined || v === '' ? null : Number(v));

export function money(v, { decimals } = {}) {
  const n = num(v);
  if (n === null || Number.isNaN(n)) return '—';
  const d = decimals !== undefined ? decimals : (Math.abs(n) >= 1000 ? 0 : 2);
  // Sign BEFORE the currency symbol: "−$2.91", never "$-2.91".
  return (n < 0 ? '\u2212$' : '$')
    + Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
}

// Typographic minus for negatives, explicit plus for positives. Used everywhere a
// change is shown so the sign is never ambiguous.
export function signedPct(v, digits = 1) {
  const n = num(v);
  if (n === null || Number.isNaN(n)) return '—';
  return (n < 0 ? '\u2212' : '+') + Math.abs(n).toFixed(digits) + '%';
}

export function plainPct(v, digits = 1) {
  const n = num(v);
  if (n === null || Number.isNaN(n)) return '—';
  return n.toFixed(digits) + '%';
}

// A 0..1 ratio rendered as a percentage. Never assume the caller pre-multiplied.
export function ratioPct(v, digits = 1) {
  const n = num(v);
  if (n === null || Number.isNaN(n)) return '—';
  return (n * 100).toFixed(digits) + '%';
}

export function shortDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(String(iso).replace('Z', '') + 'Z');
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10);
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  } catch (e) { return String(iso).slice(0, 10); }
}

export function timeAgo(iso) {
  if (!iso) return '';
  const t = Date.now() - new Date(String(iso).replace('Z', '') + 'Z').getTime();
  if (Number.isNaN(t)) return '';
  const m = Math.floor(t / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

/* ------------------------- knowledge + status ------------------------- */
// The six knowledge kinds stay visibly distinct — they are deliberately NOT
// collapsible into one confidence score.
export const KNOWLEDGE = {
  OBSERVED_FACT: { label: 'Observed', icon: Eye, cls: 'text-emerald-300 ring-emerald-500/30',
    hint: 'Measured directly by this system.' },
  REPORTED_FACT: { label: 'Reported', icon: FileText, cls: 'text-sky-300 ring-sky-500/30',
    hint: 'Published by a third party, usually with a lag.' },
  SYSTEM_ASSESSMENT: { label: 'Assessment', icon: Cpu, cls: 'text-violet-300 ring-violet-500/30',
    hint: 'A versioned rule applied to observed evidence — a product rule, not a market law.' },
  ALBERT_INTERPRETATION: { label: 'Albert’s reading', icon: MessageCircle, cls: 'text-amber-300 ring-amber-500/30',
    hint: 'Albert explaining authoritative values. He never invents numbers.' },
  WHAT_IF_ASSUMPTION: { label: 'Assumption', icon: Beaker, cls: 'text-fuchsia-300 ring-fuchsia-500/30',
    hint: 'Your assumption, not an observation. It changes nothing in your account.' },
  UNKNOWN: { label: 'Not known', icon: HelpCircle, cls: 'text-slate-400 ring-slate-600/40',
    hint: 'The system cannot establish this. Absence of evidence, not a neutral reading.' },
};

export function KnowledgeBadge({ kind, className = '' }) {
  const k = KNOWLEDGE[kind] || KNOWLEDGE.UNKNOWN;
  const Icon = k.icon;
  return (
    <span title={k.hint}
      className={`inline-flex shrink-0 items-center gap-1 rounded-full bg-slate-950/70 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ${k.cls} ${className}`}>
      <Icon className="h-3 w-3" />{k.label}
    </span>
  );
}

export const STATUS_META = {
  FRESH: { label: 'Fresh', cls: 'text-emerald-300 ring-emerald-500/30' },
  PARTIAL: { label: 'Partial', cls: 'text-amber-300 ring-amber-500/30' },
  STALE: { label: 'Stale', cls: 'text-amber-300 ring-amber-500/30' },
  MISSING: { label: 'Unavailable', cls: 'text-slate-300 ring-slate-600/40' },
  UNSUPPORTED: { label: 'Not supported', cls: 'text-slate-400 ring-slate-600/40' },
  ERROR: { label: 'Error', cls: 'text-red-300 ring-red-500/30' },
};

export function StatusBadge({ status, note, className = '' }) {
  if (!status) return null;
  const s = STATUS_META[status] || STATUS_META.MISSING;
  return (
    <span title={note || undefined}
      className={`inline-flex shrink-0 items-center gap-1 rounded-full bg-slate-950/70 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ${s.cls} ${className}`}>
      {s.label}{note ? ` · ${note}` : ''}
    </span>
  );
}

/* --------------------------- evidence links --------------------------- */
// Every material claim gets one of these. It resolves the EXACT snapshot the claim
// was made from — never a landing page that merely looks related.
export function EvidenceButton({ snapshotId, label = 'Evidence', onEvidence, className = '' }) {
  if (!snapshotId || !onEvidence) return null;
  return (
    <button type="button" onClick={() => onEvidence(snapshotId)}
      title="Open the exact snapshot this statement was made from"
      className={`inline-flex shrink-0 items-center gap-1 text-[11px] font-semibold text-sky-400 underline decoration-sky-500/40 underline-offset-2 hover:text-sky-300 ${className}`}>
      <ShieldCheck className="h-3 w-3" />{label}
    </button>
  );
}

// A figure that is itself a link to its evidence — used for the validation facts on
// the chart, where a number without its source would be worthless.
export function EvidenceFact({ value, label, snapshotId, onEvidence, tone = 'default' }) {
  const toneCls = tone === 'warn' ? 'text-amber-300' : tone === 'good' ? 'text-emerald-300' : 'text-white';
  const clickable = !!(snapshotId && onEvidence);
  return (
    <button type="button" disabled={!clickable}
      onClick={clickable ? () => onEvidence(snapshotId) : undefined}
      className={`group min-w-0 rounded-lg border border-slate-800 bg-slate-950/60 px-2.5 py-1.5 text-left ${clickable ? 'hover:border-sky-500/50' : 'cursor-default'}`}>
      <p className={`truncate text-[13px] font-bold ${toneCls}`}>{value}</p>
      <p className="truncate text-[10px] leading-tight text-slate-500 group-hover:text-slate-400">{label}</p>
    </button>
  );
}

/* ------------------------------ layout ------------------------------ */
export function StreamHeader({ icon: Icon, title, subtitle, accent = 'sky', right }) {
  const ring = accent === 'violet' ? 'ring-violet-500/25' : 'ring-sky-500/25';
  const text = accent === 'violet' ? 'text-violet-300' : 'text-sky-300';
  return (
    <div className={`flex items-center gap-2.5 rounded-xl bg-slate-950/60 px-3.5 py-2.5 ring-1 ${ring}`}>
      {Icon ? <Icon className={`h-4 w-4 shrink-0 ${text}`} /> : null}
      <div className="min-w-0">
        <h2 className="truncate text-[13px] font-bold uppercase tracking-wider text-white">{title}</h2>
        {subtitle ? <p className="truncate text-[11px] text-slate-500">{subtitle}</p> : null}
      </div>
      {right ? <div className="ml-auto shrink-0">{right}</div> : null}
    </div>
  );
}

export function Limitations({ items, className = '' }) {
  const list = (items || []).filter(Boolean);
  if (!list.length) return null;
  return (
    <ul className={`space-y-1 text-[11px] leading-relaxed text-slate-500 ${className}`}>
      {list.map((l, i) => (
        <li key={i} className="flex gap-1.5"><span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-slate-600" /><span>{l}</span></li>
      ))}
    </ul>
  );
}

/* ------------------------------- hooks ------------------------------- */
// Real pixel width, so chart text is rendered at its true size instead of being
// scaled by a viewBox (which makes labels illegible on a laptop).
export function useElementWidth(fallback = 900) {
  const ref = useRef(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const measure = () => setW(Math.max(280, Math.round(el.clientWidth || fallback)));
    measure();
    let ro = null;
    try {
      ro = new ResizeObserver(measure);
      ro.observe(el);
    } catch (e) {
      window.addEventListener('resize', measure);
    }
    return () => {
      if (ro) ro.disconnect();
      else window.removeEventListener('resize', measure);
    };
  }, [fallback]);
  return [ref, w];
}
