'use client';

import React from 'react';
import { Volume2, VolumeX, ExternalLink, BellPlus, Check } from 'lucide-react';
import { API_BASE } from '../lib/api';

// Pull dollar levels Albert mentions (e.g. "$74,000", "$77411") so we can offer
// one-tap price alerts for them.
function extractLevels(text) {
  const out = [];
  const seen = new Set();
  const re = /\$\s?(\d{1,3}(?:,\d{3})+|\d{4,7})(?:\.\d+)?/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const n = Number(m[1].replace(/,/g, ''));
    if (n >= 100 && !seen.has(n)) { seen.add(n); out.push(n); }
  }
  return out.slice(0, 5);
}

export default function AlbertReplyMeta({ text, sources = [], symbol = 'BTC', pid = '' }) {
  const [speaking, setSpeaking] = React.useState(false);
  const [alerted, setAlerted] = React.useState({});
  const levels = React.useMemo(() => extractLevels(text || ''), [text]);

  React.useEffect(() => () => { try { window.speechSynthesis?.cancel(); } catch (e) { /* noop */ } }, []);

  const speak = () => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return;
    const synth = window.speechSynthesis;
    if (speaking) { synth.cancel(); setSpeaking(false); return; }
    const clean = String(text || '').replace(/[#*`_>]/g, '').replace(/\s+/g, ' ').trim();
    const u = new SpeechSynthesisUtterance(clean.slice(0, 4000));
    u.rate = 1.02;
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    synth.cancel();
    synth.speak(u);
    setSpeaking(true);
  };

  const setAlert = async (level) => {
    try {
      await fetch(`${API_BASE}/v1/price-alert`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid, asset: symbol, level }),
      });
      setAlerted((a) => ({ ...a, [level]: true }));
    } catch (e) { /* noop */ }
  };

  return (
    <div className="mt-2 space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <button onClick={speak}
          className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-800/60 px-2 py-0.5 text-[11px] font-medium text-slate-300 transition-colors hover:text-white">
          {speaking ? <><VolumeX className="h-3 w-3" />Stop</> : <><Volume2 className="h-3 w-3" />Listen</>}
        </button>
        {levels.map((lv) => (
          <button key={lv} onClick={() => setAlert(lv)} disabled={!!alerted[lv]}
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors ${alerted[lv] ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300' : 'border-sky-600/40 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20'}`}>
            {alerted[lv] ? <><Check className="h-3 w-3" />Alerting ${lv.toLocaleString()}</> : <><BellPlus className="h-3 w-3" />Alert @ ${lv.toLocaleString()}</>}
          </button>
        ))}
      </div>
      {sources && sources.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] uppercase tracking-wide text-slate-500">Sources</span>
          {sources.map((s, i) => (
            <a key={i} href={s.url} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-800/40 px-2 py-0.5 text-[11px] text-slate-400 transition-colors hover:text-sky-300">
              <ExternalLink className="h-3 w-3" />{(s.title || 'source').slice(0, 28)}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
