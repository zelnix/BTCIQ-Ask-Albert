'use client';
// Voice input for Ask-Albert. Uses the browser's built-in Web Speech API
// (SpeechRecognition) — no backend, no API key. Transcribes speech into the
// chat input live. Auto-hides when the browser doesn't support it.
import React from 'react';
import { Mic, MicOff } from 'lucide-react';

function getRecognition() {
  if (typeof window === 'undefined') return null;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  return SR ? new SR() : null;
}

export default function MicButton({ value, onChange, disabled, onError, size = 'md' }) {
  const [supported, setSupported] = React.useState(false);
  const [listening, setListening] = React.useState(false);
  const recRef = React.useRef(null);
  const baseRef = React.useRef('');

  React.useEffect(() => {
    const SR = (typeof window !== 'undefined') && (window.SpeechRecognition || window.webkitSpeechRecognition);
    setSupported(Boolean(SR));
    return () => { try { recRef.current && recRef.current.abort(); } catch (e) { /* noop */ } };
  }, []);

  const stop = () => { try { recRef.current && recRef.current.stop(); } catch (e) { /* noop */ } setListening(false); };

  const start = () => {
    if (disabled) return;
    const rec = getRecognition();
    if (!rec) { setSupported(false); return; }
    recRef.current = rec;
    rec.lang = 'en-US';
    rec.continuous = false;
    rec.interimResults = true;
    baseRef.current = (value || '').trim();
    rec.onresult = (e) => {
      let txt = '';
      for (let i = 0; i < e.results.length; i += 1) txt += e.results[i][0].transcript;
      const base = baseRef.current;
      onChange((base ? base + ' ' : '') + txt.trim());
    };
    rec.onerror = (e) => { setListening(false); if (onError) onError(e && e.error); };
    rec.onend = () => setListening(false);
    try { rec.start(); setListening(true); } catch (e) { setListening(false); }
  };

  if (!supported) return null;
  const px = size === 'sm' ? 'h-4 w-4' : 'h-[18px] w-[18px]';
  return (
    <button
      type="button"
      onClick={listening ? stop : start}
      disabled={disabled}
      title={listening ? 'Stop listening' : 'Speak your question'}
      className={`relative flex items-center justify-center rounded-full p-1.5 transition-colors disabled:opacity-40 ${listening ? 'bg-rose-500/15 text-rose-400' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`}
    >
      {listening && <span className="absolute inset-0 animate-ping rounded-full bg-rose-500/30" />}
      {listening ? <MicOff className={px} /> : <Mic className={px} />}
    </button>
  );
}
