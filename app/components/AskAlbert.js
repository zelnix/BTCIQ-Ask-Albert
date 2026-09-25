'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  Send, Loader2, ShieldCheck, ChevronDown, Sparkles, Activity, Wallet, FlaskConical,
  Database, MessageCircle, Info,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { API_BASE } from '../lib/api';

const FRESH_COLOR = { FRESH: 'text-emerald-400', STALE: 'text-amber-400', MISSING: 'text-red-400', UNKNOWN: 'text-slate-400' };
const money = (v) => {
  const n = v == null || v === '' ? null : Number(v);
  if (n == null || Number.isNaN(n)) return '—';
  return '$' + n.toLocaleString(undefined, { maximumFractionDigits: n >= 1000 ? 0 : 2 });
};
function sectionFromDeepLink(dl) {
  if (!dl) return null;
  try { return new URLSearchParams(dl.split('?')[1] || '').get('section'); } catch (e) { return null; }
}
const STARTERS = [
  'How is my paper account doing right now?',
  'What is the market doing, and what does it mean for me?',
  'Why hasn’t anything traded recently?',
  'Show me my strategies and what would make Albert act.',
];

function EvidenceRow({ evidence, onNav }) {
  if (!evidence || !evidence.length) return null;
  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
      {evidence.map((e, i) => {
        const sec = sectionFromDeepLink(e.deepLink);
        const fc = FRESH_COLOR[e.freshness] || FRESH_COLOR.UNKNOWN;
        return (
          <button key={i} onClick={() => sec && onNav && onNav(sec)}
            title={`${e.sourceId || ''}${e.asOf ? ` · ${e.asOf}` : ''}`}
            className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-900/70 px-2 py-0.5 text-[10px] font-semibold text-sky-300 hover:border-sky-500/50 hover:text-sky-200">
            <ShieldCheck className="h-3 w-3" />{(e.label || 'evidence').replace(/_/g, ' ')}
            <span className={`ml-0.5 ${fc}`}>·{e.freshness || '?'}</span>
          </button>
        );
      })}
    </div>
  );
}

function TechnicalDetails({ msg }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button onClick={() => setOpen((o) => !o)} className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500 hover:text-slate-300">
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />Technical details
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5 rounded-lg border border-slate-800 bg-slate-950/60 p-2.5 text-[11px] text-slate-400">
          <p><span className="text-slate-500">Model:</span> <span className="font-mono text-slate-300">{msg.model || '—'}</span></p>
          <p><span className="text-slate-500">Read functions consulted:</span> {(msg.contextFunctions || []).join(', ') || 'none'}</p>
          {(msg.evidence || []).length > 0 && (
            <div>
              <p className="text-slate-500">Evidence sources:</p>
              <ul className="mt-0.5 space-y-0.5">
                {msg.evidence.map((e, i) => (
                  <li key={i} className="font-mono text-slate-300">{e.sourceId} · {e.freshness} · asOf {e.asOf || 'n/a'}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatePanel({ sop }) {
  if (!sop) return null;
  const m = sop.market || {}; const p = sop.portfolio || {}; const pa = sop.paper || {};
  const dq = sop.dataQuality?.status || 'HEALTHY';
  const Row = ({ icon: Icon, label, value, color }) => (
    <div className="flex items-center gap-2.5 rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2">
      <Icon className="h-4 w-4 shrink-0 text-slate-500" />
      <div className="min-w-0 flex-1"><p className="text-[10px] uppercase tracking-wider text-slate-500">{label}</p><p className={`truncate text-sm font-bold ${color || 'text-white'}`}>{value}</p></div>
    </div>
  );
  return (
    <div className="space-y-2.5">
      <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400"><Info className="h-3.5 w-3.5" />Current state Albert can see</p>
      <Row icon={Activity} label="Market stance" value={m.regime || 'Unknown'} color={m.freshness === 'FRESH' ? 'text-emerald-400' : 'text-amber-400'} />
      <Row icon={Wallet} label="Paper value" value={money(p.totalValue)} />
      <Row icon={FlaskConical} label="Mode" value={pa.mode || '—'} />
      <Row icon={Database} label="Data status" value={dq === 'HEALTHY' ? 'Healthy' : dq === 'DEGRADED' ? 'Degraded' : 'Limited'} color={dq === 'HEALTHY' ? 'text-emerald-400' : dq === 'BLOCKED' ? 'text-red-400' : 'text-amber-400'} />
      <p className="text-[10px] leading-relaxed text-slate-600">Albert answers strictly from this owner-scoped, paper-only state. He never invents numbers, and cannot place, change or approve trades.</p>
    </div>
  );
}

export default function AskAlbert({ onNav }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [entity, setEntity] = useState(null);
  const [sop, setSop] = useState(null);
  const endRef = useRef(null);
  const sessionId = useRef('ask_' + Math.random().toString(36).slice(2, 10));

  useEffect(() => {
    fetch(`${API_BASE}/v1/albert/state-of-play`, { credentials: 'include', cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null)).then((j) => j && setSop(j)).catch(() => {});
  }, [messages.length]);

  const send = useCallback(async (text, ent) => {
    const q = (text ?? input).trim();
    if (!q || sending) return;
    setInput('');
    const useEnt = ent !== undefined ? ent : entity;
    setMessages((m) => [...m, { role: 'user', text: q }]);
    setSending(true);
    try {
      const r = await fetch(`${API_BASE}/v1/albert/ask`, {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: q, session_id: sessionId.current, entity: useEnt || undefined }),
      });
      if (r.status === 401 || r.status === 403) {
        setMessages((m) => [...m, { role: 'albert', text: 'Please sign in to talk with Albert.' }]);
      } else {
        const j = await r.json();
        setMessages((m) => [...m, { role: 'albert', text: j.reply || 'No answer came back.',
          evidence: j.evidence, model: j.model, contextFunctions: j.contextFunctions }]);
      }
    } catch (e) {
      setMessages((m) => [...m, { role: 'albert', text: 'Network error — please try again.' }]);
    } finally {
      setSending(false); setEntity(null);
    }
  }, [input, sending, entity]);

  // Prefilled handoff: another screen opened Ask Albert with a question + entity.
  useEffect(() => {
    let pending = null;
    try { pending = window.__albertPendingAsk; window.__albertPendingAsk = null; } catch (e) { /* noop */ }
    if (pending && (pending.question || pending.entity)) {
      setEntity(pending.entity || null);
      if (pending.question) send(pending.question, pending.entity || null);
      else setInput(pending.prefill || '');
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, sending]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2.5">
        <MessageCircle className="h-5 w-5 text-sky-400" />
        <h1 className="text-lg font-bold text-white">Ask Albert</h1>
        <span className="text-[12px] text-slate-500">Your context-aware trading companion · paper only</span>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Conversation */}
        <div className="lg:col-span-2">
          <Card className="flex min-h-[62vh] flex-col border-0 bg-slate-900 p-0 ring-1 ring-slate-800">
            <div className="flex-1 space-y-4 overflow-y-auto p-5">
              {messages.length === 0 && (
                <div className="rounded-xl border border-sky-500/20 bg-sky-500/[0.05] p-4">
                  <div className="flex items-center gap-2.5">
                    <img src="/albert.png" alt="Albert" className="h-9 w-9 rounded-full object-cover ring-2 ring-sky-500/40" />
                    <p className="text-sm text-slate-200">Ask me about your market state, portfolio, a decision, a strategy or a paper trade. I explain in plain English and link the exact evidence.</p>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {STARTERS.map((s) => (
                      <button key={s} onClick={() => send(s)} className="rounded-full border border-slate-700 bg-slate-950/60 px-3 py-1.5 text-[12px] text-slate-300 hover:border-sky-500/50 hover:text-sky-200">{s}</button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((m, i) => (
                m.role === 'user' ? (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-sky-600 px-3.5 py-2 text-sm text-white">{m.text}</div>
                  </div>
                ) : (
                  <div key={i} className="flex gap-2.5">
                    <img src="/albert.png" alt="Albert" className="h-8 w-8 shrink-0 rounded-full object-cover ring-1 ring-sky-500/40" />
                    <div className="min-w-0 flex-1 rounded-2xl rounded-tl-sm bg-slate-800/60 px-3.5 py-2.5">
                      <p className="max-w-[70ch] whitespace-pre-wrap text-[14px] leading-relaxed text-slate-100">{m.text}</p>
                      <EvidenceRow evidence={m.evidence} onNav={onNav} />
                      {(m.model || (m.evidence || []).length > 0) && <TechnicalDetails msg={m} />}
                    </div>
                  </div>
                )
              ))}
              {sending && (
                <div className="flex items-center gap-2 text-[13px] text-slate-400"><Loader2 className="h-4 w-4 animate-spin" />Albert is thinking…</div>
              )}
              <div ref={endRef} />
            </div>
            <div className="border-t border-slate-800 p-3">
              {entity && <div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-violet-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-violet-300"><Sparkles className="h-3 w-3" />Context: {entity.type} attached</div>}
              <div className="flex items-end gap-2">
                <textarea rows={1} value={input} onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                  placeholder="Ask Albert about your state, a decision, a strategy or a paper trade…"
                  className="max-h-32 flex-1 resize-none rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-slate-100 outline-none focus:border-sky-500" />
                <Button onClick={() => send()} disabled={sending || !input.trim()} className="h-10 gap-1.5 bg-gradient-to-r from-sky-500 to-violet-600 text-white hover:from-sky-400 hover:to-violet-500">
                  {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}Send
                </Button>
              </div>
            </div>
          </Card>
        </div>

        {/* State + evidence side panel (desktop/laptop) */}
        <div className="hidden lg:block">
          <Card className="border-0 bg-slate-900 p-4 ring-1 ring-slate-800"><StatePanel sop={sop} /></Card>
          <p className="mt-3 px-1 text-center text-[11px] text-slate-600">Paper trading only — Albert has read-only visibility. He explains the deterministic engine; he never invents or alters trades.</p>
        </div>
      </div>
    </div>
  );
}
