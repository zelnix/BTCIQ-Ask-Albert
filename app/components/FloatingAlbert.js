'use client';

import React from 'react';
import { Button } from '@/components/ui/button';
import { Maximize2, X, Clock, Send } from 'lucide-react';
import { API_BASE } from '../lib/api';

// Human-readable scope label per screen, so the floating chat can tell Albert
// (and the user) which screen the conversation is grounded in.
const SECTION_LABELS = {
  overview: 'all things BTCIQ', forecasts: 'Forecasts', 'market-intel': 'Market Intelligence',
  crossmarket: 'Cross-Market', analogs: 'Happening Again', smartmoney: 'Smart Money',
  whales: 'Whale Watch', institutional: 'Institutional & Derivatives', leverage: 'Leverage',
  macro: 'Macro & Policy', news: 'News', risk: 'Risk', events: 'Events',
  performance: 'Performance', timemachine: 'Time Machine', network: 'Network & Sentiment',
  dataaudit: 'Data Audit', admin: 'Admin', settings: 'Settings', alerts: 'Alerts',
};

// Floating, screen-aware Ask Albert widget (present on every screen).
export default function FloatingAlbert({ active, symbol, onExpand }) {
  const [open, setOpen] = React.useState(false);
  const [sessionId] = React.useState(() => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2)));
  const [messages, setMessages] = React.useState([]);
  const [input, setInput] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [rateUntil, setRateUntil] = React.useState(0);
  const [, setRateTick] = React.useState(0);
  const endRef = React.useRef(null);
  const isOverview = !active || active === 'overview';
  const scopeLabel = SECTION_LABELS[active] || 'all things BTCIQ';

  React.useEffect(() => { if (open) endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading, open]);
  // Reset the mini-thread when the user switches screens so context stays relevant.
  React.useEffect(() => { setMessages([]); }, [active]);
  React.useEffect(() => {
    if (!rateUntil) return;
    const id = setInterval(() => {
      if (Date.now() >= rateUntil) setRateUntil(0);
      else setRateTick((t) => t + 1);
    }, 1000);
    return () => clearInterval(id);
  }, [rateUntil]);
  const rateSecondsLeft = rateUntil ? Math.max(0, Math.ceil((rateUntil - Date.now()) / 1000)) : 0;

  const suggestions = isOverview
    ? ['Give me the 10-second read on Bitcoin right now.', 'What is the biggest risk today?', "What's moving the market?"]
    : [`Give me a quick read on this ${scopeLabel} screen.`, `What should I watch on ${scopeLabel}?`, `What's the key signal here?`];

  const send = async (text) => {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', text: msg }]);
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/v1/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: msg, symbol, section: active }),
      });
      if (r.status === 429) {
        const j = await r.json().catch(() => ({}));
        const secs = Math.max(1, Math.min(120, Number(j.retry_in) || 30));
        setLoading(false);
        setMessages((m) => m.slice(0, -1));
        setInput(msg);
        setRateUntil(Date.now() + secs * 1000);
        return;
      }
      const j = await r.json();
      if (j && j.status === 'rate_limited') {
        const secs = Math.max(1, Math.min(120, Number(j.retry_in) || 30));
        setLoading(false);
        setMessages((m) => m.slice(0, -1));
        setInput(msg);
        setRateUntil(Date.now() + secs * 1000);
        return;
      }
      setRateUntil(0);
      setMessages((m) => [...m, { role: 'assistant', text: j.text || 'Sorry, I could not answer that just now.' }]);
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', text: 'Network error — please try again.' }]);
    } finally { setLoading(false); }
  };

  return (
    <>
      {/* Launcher */}
      {!open && (
        <button onClick={() => setOpen(true)} title="Ask Albert"
          className="fixed bottom-5 right-5 z-50 flex items-center gap-2 rounded-full border border-sky-500/40 bg-gradient-to-r from-sky-500 to-violet-600 py-2 pl-2 pr-4 text-white shadow-lg shadow-violet-500/30 transition-transform hover:scale-105">
          <img src="/albert.png" alt="Albert" className="h-8 w-8 rounded-full object-cover ring-2 ring-white/30" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
          <span className="text-sm font-semibold">Ask Albert</span>
        </button>
      )}
      {/* Panel */}
      {open && (
        <div className="fixed bottom-5 right-5 z-50 flex h-[540px] w-[92vw] max-w-[400px] flex-col overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl shadow-black/50 ring-1 ring-slate-800">
          <div className="flex items-center gap-2.5 border-b border-slate-800 bg-slate-950/60 px-4 py-3">
            <img src="/albert.png" alt="Albert" className="h-8 w-8 rounded-full object-cover ring-2 ring-sky-500/40" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-white">Ask Albert</p>
              <p className="truncate text-[10px] text-sky-400">{isOverview ? 'Talking about all things BTCIQ' : `Focused on: ${scopeLabel}`}</p>
            </div>
            {onExpand && <button onClick={() => { setOpen(false); onExpand(); }} title="Open full chat" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"><Maximize2 className="h-4 w-4" /></button>}
            <button onClick={() => setOpen(false)} title="Close" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"><X className="h-4 w-4" /></button>
          </div>
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {messages.length === 0 && (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
                <img src="/albert.png" alt="Albert" className="h-14 w-14 rounded-full object-cover ring-2 ring-sky-500/40" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                <p className="text-sm font-semibold text-slate-200">{isOverview ? "Hi, I'm Albert — ask me anything about Bitcoin" : `Ask me about the ${scopeLabel} screen`}</p>
                <p className="max-w-[16rem] text-[11px] text-slate-500">I only use the live dashboard numbers — I won't invent data.</p>
                <div className="flex flex-col gap-1.5">
                  {suggestions.map((s, i) => (
                    <button key={i} onClick={() => send(s)} className="rounded-full border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-[11px] text-slate-300 hover:border-sky-500/40 hover:text-sky-300">{s}</button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`flex items-end gap-2 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {m.role === 'assistant' && <img src="/albert.png" alt="Albert" className="h-6 w-6 shrink-0 rounded-full object-cover ring-1 ring-sky-500/30" onError={(e) => { e.currentTarget.style.display = 'none'; }} />}
                <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-[13px] leading-relaxed ${m.role === 'user' ? 'bg-sky-500/15 text-sky-50 ring-1 ring-sky-500/25' : 'bg-slate-950/60 text-slate-200 ring-1 ring-slate-800'}`}>{m.text}</div>
              </div>
            ))}
            {loading && (
              <div className="flex items-end justify-start gap-2">
                <img src="/albert.png" alt="Albert" className="h-6 w-6 shrink-0 rounded-full object-cover ring-1 ring-sky-500/30" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                <div className="flex items-center gap-1.5 rounded-2xl bg-slate-950/60 px-3 py-2.5 ring-1 ring-slate-800">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-sky-400" style={{ animationDelay: '0ms' }} />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-sky-400" style={{ animationDelay: '150ms' }} />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-sky-400" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
          <div className="border-t border-slate-800 p-2.5">
            {rateSecondsLeft > 0 && (
              <div className="mb-2 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-[11px] leading-snug text-amber-300">
                <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>Chatting a little fast — try again in <span className="font-semibold tabular-nums">{rateSecondsLeft}s</span>.</span>
              </div>
            )}
            <div className="flex items-end gap-2">
              <textarea value={input} onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                rows={1} placeholder={isOverview ? 'Ask about Bitcoin…' : `Ask about ${scopeLabel}…`}
                className="max-h-24 flex-1 resize-none rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-[13px] text-slate-100 placeholder-slate-500 focus:border-sky-500/50 focus:outline-none" />
              <Button onClick={() => send()} disabled={loading || !input.trim() || rateSecondsLeft > 0} size="sm" className="bg-sky-500 hover:bg-sky-400"><Send className="h-4 w-4" /></Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
