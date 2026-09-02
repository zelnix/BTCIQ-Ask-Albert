// Albert's voice — primary path is server-side Google Gemini TTS (a consistent,
// device-independent "warm, well-aged professor" voice). If that fails or is
// unavailable, we gracefully fall back to the browser's SpeechSynthesis with a
// tuned mature-male profile.

import { API_BASE } from './api';

/* ------------------------- browser fallback voice ------------------------- */
const PREF = [
  /daniel/i,
  /arthur|oliver|rishi/i,
  /google uk english male/i,
  /(guy|davis|george|ryan|christopher|eric|brian|tony).*natural/i,
  /microsoft (guy|davis|george|ryan|mark)/i,
  /alex\b/i,
  /google us english/i,
  /\bmale\b/i,
];

export function pickAlbertVoice(synth) {
  let voices = [];
  try { voices = synth.getVoices() || []; } catch (e) { voices = []; }
  const en = voices.filter((v) => /^en(\b|[-_])/i.test(v.lang || ''));
  const pool = en.length ? en : voices;
  for (const rx of PREF) {
    const hit = pool.find((v) => rx.test(v.name || ''));
    if (hit) return hit;
  }
  return pool.find((v) => /natural|neural|enhanced|premium/i.test(v.name || '')) || pool[0] || null;
}

export function applyAlbertVoice(u, synth) {
  try {
    const v = pickAlbertVoice(synth);
    if (v) u.voice = v;
  } catch (e) { /* noop */ }
  u.rate = 0.93;
  u.pitch = 0.88;
  u.volume = 1;
  return u;
}

/* --------------------------- shared playback --------------------------- */
let _audio = null;         // current HTMLAudioElement (Gemini path)
let _usingBrowser = false; // whether the browser synth is currently speaking

function stripMarkup(text) {
  return String(text || '').replace(/[#*`_>]/g, '').replace(/\s+/g, ' ').trim();
}

export function stopAlbert() {
  try { if (_audio) { _audio.pause(); _audio.src = ''; _audio = null; } } catch (e) { /* noop */ }
  try { if (typeof window !== 'undefined' && window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) { /* noop */ }
  _usingBrowser = false;
}

function browserSpeak(text, onEnd) {
  try {
    if (typeof window === 'undefined' || !window.speechSynthesis) { onEnd && onEnd(); return; }
    const synth = window.speechSynthesis;
    const u = new SpeechSynthesisUtterance(stripMarkup(text).slice(0, 4000));
    applyAlbertVoice(u, synth);
    u.onend = () => { _usingBrowser = false; onEnd && onEnd(); };
    u.onerror = () => { _usingBrowser = false; onEnd && onEnd(); };
    _usingBrowser = true;
    synth.cancel();
    synth.speak(u);
  } catch (e) { _usingBrowser = false; onEnd && onEnd(); }
}

// Speak `text` as Albert. Tries Gemini TTS first, falls back to the browser voice.
// Returns nothing; call stopAlbert() to stop. onEnd fires when playback finishes
// (or immediately if nothing could play).
export async function speakAlbert(text, { onEnd } = {}) {
  stopAlbert();
  const clean = stripMarkup(text);
  if (!clean) { onEnd && onEnd(); return; }
  try {
    const res = await fetch(`${API_BASE}/v1/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: clean }),
    });
    if (!res.ok) throw new Error('tts http ' + res.status);
    const data = await res.json();
    if (!data || !data.audio_base64) throw new Error('no audio');
    const audio = new Audio(`data:${data.mime_type || 'audio/wav'};base64,${data.audio_base64}`);
    _audio = audio;
    audio.onended = () => { if (_audio === audio) _audio = null; onEnd && onEnd(); };
    audio.onerror = () => {
      if (_audio === audio) _audio = null;
      // Fall back to the browser voice if the data URL fails to play.
      browserSpeak(clean, onEnd);
    };
    await audio.play();
  } catch (e) {
    // Any network/API failure → browser fallback so "Listen" always works.
    browserSpeak(clean, onEnd);
  }
}
