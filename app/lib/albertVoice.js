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
  u.rate = 1.05;   // lively, animated — an excited professor
  u.pitch = 1.0;   // energetic but still warm
  u.volume = 1;
  return u;
}

/* --------------------------- shared playback --------------------------- */
let _audio = null;         // current HTMLAudioElement (Gemini path)
let _usingBrowser = false; // whether the browser synth is currently speaking

function stripMarkup(text) {
  return String(text || '').replace(/[#*`_>]/g, '').replace(/\s+/g, ' ').trim();
}

let _stopFlag = false;

export function stopAlbert() {
  _stopFlag = true;
  try { if (_audio) { _audio.pause(); _audio.src = ''; _audio = null; } } catch (e) { /* noop */ }
  try { if (typeof window !== 'undefined' && window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) { /* noop */ }
  _usingBrowser = false;
}

// Split text into speak-able chunks. The FIRST chunk is just one sentence so audio
// can start almost immediately; the rest are grouped (~220 chars) and prefetched
// while Albert is already talking.
function chunkText(text) {
  const sentences = (text.match(/[^.!?]+[.!?]+|\S[^.!?]*$/g) || [text])
    .map((s) => s.trim()).filter(Boolean);
  if (sentences.length === 0) return [text];
  const chunks = [sentences[0]];
  let buf = '';
  for (let i = 1; i < sentences.length; i++) {
    if (buf && (buf + ' ' + sentences[i]).length > 220) { chunks.push(buf); buf = sentences[i]; }
    else buf = (buf ? buf + ' ' : '') + sentences[i];
  }
  if (buf) chunks.push(buf);
  return chunks;
}

async function fetchTTS(text) {
  const res = await fetch(`${API_BASE}/v1/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error('tts http ' + res.status);
  const data = await res.json();
  if (!data || !data.audio_base64) throw new Error('no audio');
  return `data:${data.mime_type || 'audio/wav'};base64,${data.audio_base64}`;
}

function playUrl(url, onStart) {
  return new Promise((resolve, reject) => {
    const audio = new Audio(url);
    _audio = audio;
    if (onStart) audio.onplaying = onStart;
    audio.onended = () => resolve();
    audio.onerror = () => reject(new Error('play error'));
    const p = audio.play();
    if (p && p.catch) p.catch(reject);
  });
}

function browserSpeak(text, onStart, onEnd) {
  try {
    if (typeof window === 'undefined' || !window.speechSynthesis) { onEnd && onEnd(); return; }
    const synth = window.speechSynthesis;
    const u = new SpeechSynthesisUtterance(stripMarkup(text).slice(0, 4000));
    applyAlbertVoice(u, synth);
    u.onstart = () => { onStart && onStart(); };
    u.onend = () => { _usingBrowser = false; onEnd && onEnd(); };
    u.onerror = () => { _usingBrowser = false; onEnd && onEnd(); };
    _usingBrowser = true;
    synth.cancel();
    synth.speak(u);
    setTimeout(() => { if (_usingBrowser) onStart && onStart(); }, 400);
  } catch (e) { _usingBrowser = false; onEnd && onEnd(); }
}

// Speak `text` as Albert. Generates the first sentence fast to start quickly, and
// fires ALL remaining chunks in parallel so playback is gapless (no mid-text pause).
// onStart fires when audio actually begins; onEnd when everything finishes.
export async function speakAlbert(text, { onStart, onEnd } = {}) {
  stopAlbert();
  _stopFlag = false;
  const clean = stripMarkup(text);
  if (!clean) { onEnd && onEnd(); return; }
  const chunks = chunkText(clean);
  let started = false;
  const fireStart = () => { if (!started) { started = true; onStart && onStart(); } };
  // Kick off every chunk's generation at once so later chunks are ready in time.
  const jobs = chunks.map((c) => fetchTTS(c).catch(() => null));
  try {
    for (let i = 0; i < chunks.length; i++) {
      const url = await jobs[i];
      if (_stopFlag) return;
      if (!url) { browserSpeak(chunks.slice(i).join(' '), started ? null : fireStart, onEnd); return; }
      try {
        await playUrl(url, fireStart);
      } catch (e) {
        browserSpeak(chunks.slice(i).join(' '), started ? null : fireStart, onEnd);
        return;
      }
      if (_stopFlag) return;
    }
    onEnd && onEnd();
  } catch (e) {
    browserSpeak(clean, onStart, onEnd);
  }
}
