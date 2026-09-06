'use client';
// Marketing landing + native Google sign-in gate for "Ask Albert".
// Shown to signed-out visitors; on successful sign-in it calls onAuthed(user).
import React, { useEffect, useRef, useState } from 'react';
import { getAuthConfig, exchangeGoogleCredential, rememberUser } from '../lib/auth';
import {
  Brain, Bell, LineChart, Mic, TrendingUp, ShieldCheck, Sparkles, Radar, Loader2,
} from 'lucide-react';

const HERO_IMG = 'https://images.unsplash.com/photo-1660165458059-57cfb6cc87e5?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NTJ8MHwxfHNlYXJjaHwxfHxibG9ja2NoYWluJTIwYWJzdHJhY3R8ZW58MHx8fGJsdWV8MTc4ODUzNDU3M3ww&ixlib=rb-4.1.0&q=85';
const DASH_IMG = 'https://images.unsplash.com/photo-1660020619062-70b16c44bf0f?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAxODF8MHwxfHNlYXJjaHwxfHxmaW5hbmNpYWwlMjBkYXNoYm9hcmR8ZW58MHx8fGJsdWV8MTc4ODUzNDU3M3ww&ixlib=rb-4.1.0&q=85';

const FEATURES = [
  { icon: TrendingUp, title: 'Targeted Morning Briefs', desc: 'Albert reads the market each morning and tells you what actually matters today — not yesterday’s noise.' },
  { icon: Radar, title: 'Alert Engine & Edge Board', desc: 'Multi-detector scans across the top coins, ranked by real backtest edge, filtered for correlation and BTC strength.' },
  { icon: LineChart, title: 'Trading Strategies', desc: 'Build strategies from a chat, track simulated performance, and compare them side-by-side.' },
  { icon: Brain, title: 'Ask Albert (Gemini)', desc: 'A character-driven AI quant that knows your engines, sectors and positions — ask him anything.' },
  { icon: Mic, title: 'Albert’s Voice', desc: 'Pick from a dozen voices and let Albert read the market aloud, highlighting each word as he speaks.' },
  { icon: Bell, title: 'Smart Nudges', desc: 'Perishable, deduped signals and discipline guardrails that keep you on your plan.' },
];

export default function HomePage({ onAuthed }) {
  const btnRef = useRef(null);
  const [clientId, setClientId] = useState('');
  const [configured, setConfigured] = useState(true);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    getAuthConfig().then((c) => {
      if (!alive) return;
      setClientId(c.client_id || '');
      setConfigured(!!c.configured);
    });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!clientId) return undefined;
    const render = () => {
      if (!window.google || !window.google.accounts || !btnRef.current) return;
      try {
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: async (resp) => {
            setErr(''); setBusy(true);
            try {
              const data = await exchangeGoogleCredential(resp.credential);
              rememberUser(data.user);
              onAuthed && onAuthed(data.user);
            } catch (e) {
              setErr(e.message || 'Sign-in failed. Please try again.');
              setBusy(false);
            }
          },
          auto_select: false,
          cancel_on_tap_outside: true,
        });
        btnRef.current.replaceChildren();
        window.google.accounts.id.renderButton(btnRef.current, {
          type: 'standard', theme: 'filled_blue', size: 'large',
          text: 'continue_with', shape: 'pill', width: 300,
        });
      } catch (e) { /* noop */ }
    };
    const existing = document.querySelector('script[src="https://accounts.google.com/gsi/client"]');
    if (existing) {
      existing.addEventListener('load', render);
      render();
      return () => existing.removeEventListener('load', render);
    }
    const s = document.createElement('script');
    s.src = 'https://accounts.google.com/gsi/client';
    s.async = true;
    s.onload = render;
    document.head.appendChild(s);
    return undefined;
  }, [clientId, onAuthed]);

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div
          className="absolute inset-0 bg-cover bg-center opacity-25"
          style={{ backgroundImage: `url(${HERO_IMG})` }}
        />
        <div className="absolute inset-0 bg-gradient-to-b from-slate-950/70 via-slate-950/85 to-slate-950" />
        <div className="relative mx-auto flex max-w-6xl flex-col items-center px-6 pb-20 pt-16 text-center">
          <div className="mb-5 flex items-center gap-3">
            <img src="/albert.png" alt="Albert" className="h-14 w-14 rounded-full ring-2 ring-sky-500/50" />
            <span className="text-lg font-semibold tracking-tight text-white">Ask Albert</span>
          </div>
          <div className="mb-4 inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-xs font-medium text-sky-300">
            <Sparkles className="h-3.5 w-3.5" /> Your Hucentai crypto quant
          </div>
          <h1 className="max-w-3xl text-4xl font-bold leading-tight tracking-tight text-white sm:text-5xl md:text-6xl">
            Meet <span className="bg-gradient-to-r from-sky-400 to-violet-400 bg-clip-text text-transparent">Albert</span> — the market, read for you every morning
          </h1>
          <p className="mt-5 max-w-2xl text-base text-slate-300 sm:text-lg">
            Targeted briefs, a multi-detector alert engine, backtested edge, and a character-driven AI quant
            that talks you through it — in a voice you choose.
          </p>
          <div className="mt-8 flex flex-col items-center gap-3">
            {configured ? (
              <div ref={btnRef} className="min-h-[44px]" />
            ) : (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
                Google sign-in isn’t configured yet. Add GOOGLE_CLIENT_ID to the backend.
              </div>
            )}
            {busy && (
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin" /> Signing you in…
              </div>
            )}
            {err && <p className="text-sm text-red-400">{err}</p>}
            <p className="max-w-xs text-[11px] text-slate-500">
              We only use your Google profile to create your account. No posting, ever.
            </p>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-6 py-14">
        <h2 className="mb-2 text-center text-2xl font-bold text-white">Everything Albert does for you</h2>
        <p className="mb-10 text-center text-sm text-slate-400">One dashboard, tuned for discipline and edge.</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
              <div className="mb-3 inline-flex rounded-xl bg-sky-500/10 p-2.5 text-sky-400">
                <f.icon className="h-5 w-5" />
              </div>
              <h3 className="mb-1 font-semibold text-white">{f.title}</h3>
              <p className="text-sm leading-relaxed text-slate-400">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Showcase */}
      <section className="mx-auto max-w-6xl px-6 pb-16">
        <div className="grid items-center gap-8 rounded-3xl border border-slate-800 bg-slate-900/50 p-6 md:grid-cols-2 md:p-10">
          <div>
            <h2 className="text-2xl font-bold text-white">A quant desk in your pocket</h2>
            <p className="mt-3 text-sm leading-relaxed text-slate-400">
              Live L2 order-flow, sector rotation, an edge-ranked board and your own tracked strategies —
              all narrated by Albert. Your watchlist, portfolio, strategies and voice preference stay tied to
              your account, on every device.
            </p>
            <ul className="mt-5 space-y-2 text-sm text-slate-300">
              <li className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-emerald-400" /> Private to your account</li>
              <li className="flex items-center gap-2"><TrendingUp className="h-4 w-4 text-sky-400" /> Backtested edge, not vibes</li>
              <li className="flex items-center gap-2"><Brain className="h-4 w-4 text-violet-400" /> Gemini-powered reasoning</li>
            </ul>
          </div>
          <div className="overflow-hidden rounded-2xl border border-slate-800">
            <img src={DASH_IMG} alt="Ask Albert dashboard" className="h-full w-full object-cover" />
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-900 py-8 text-center text-xs text-slate-600">
        Ask Albert · AI crypto intelligence. For research/education — not financial advice.
      </footer>
    </main>
  );
}
