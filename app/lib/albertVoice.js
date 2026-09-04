// Albert's voice — primary path is server-side Google Gemini TTS (a consistent,
// device-independent voice the user can pick on the "Meet Albert" screen). If that
// fails, is unavailable, or the user picked a device voice, we use the browser's
// SpeechSynthesis with a tuned mature-male profile.
//
// This module also broadcasts karaoke-style word-highlight events (see
// onAlbertHighlight) so the on-screen text can light up word-by-word as Albert reads.

import { API_BASE } from './api';

/* ============================ voice preference ============================ */
const PREF_KEY = 'albert_voice_pref';

// pref shape: { engine: 'gemini'|'browser', voice: '<GeminiVoiceName>', browserVoiceURI: '<uri>' }
export function getVoicePref() {
  try {
    const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(PREF_KEY) : null;
    const p = raw ? JSON.parse(raw) : null;
    if (p && (p.engine === 'gemini' || p.engine === 'browser')) return p;
  } catch (e) { /* noop */ }
  return { engine: 'gemini', voice: 'Charon', browserVoiceURI: '' };
}

export function setVoicePref(pref) {
  const p = { engine: 'gemini', voice: 'Charon', browserVoiceURI: '', ...(pref || {}) };
  try { localStorage.setItem(PREF_KEY, JSON.stringify(p)); } catch (e) { /* noop */ }
  // Best-effort cross-device persistence (localStorage remains the source of truth).
  try {
    fetch(`${API_BASE}/v1/albert/voice-pref`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ engine: p.engine, voice: p.voice, browser_voice_uri: p.browserVoiceURI }),
    }).catch(() => {});
  } catch (e) { /* noop */ }
  _clip.clear(); // switching voices invalidates the cached audio
  return p;
}

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
  // Honour an explicit device-voice choice first.
  try {
    const pref = getVoicePref();
    if (pref.engine === 'browser' && pref.browserVoiceURI) {
      const hit = voices.find((v) => v.voiceURI === pref.browserVoiceURI || v.name === pref.browserVoiceURI);
      if (hit) return hit;
    }
  } catch (e) { /* noop */ }
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

/* ============================ word highlighting ========================== */
// Components (AlbertText) subscribe to know which word is being read right now.
const _hlSubs = new Set();
let _hlText = '';   // the cleaned text currently being read
export function onAlbertHighlight(cb) { _hlSubs.add(cb); return () => _hlSubs.delete(cb); }
function emitHL(index, active) {
  const detail = { text: _hlText, index, active };
  _hlSubs.forEach((cb) => { try { cb(detail); } catch (e) { /* noop */ } });
}
function setWord(i) { emitHL(i, true); }
function endHL() { emitHL(-1, false); }

let _hlTimers = [];
function clearHLTimers() { _hlTimers.forEach((t) => clearTimeout(t)); _hlTimers = []; }

/* ----------------------------- text cleaning ----------------------------- */
// Clean ONE line the same way AlbertText renders it: drop heading/bullet/number
// markers and bold syntax so the spoken words line up 1:1 with the on-screen words.
export function cleanLineForSpeech(line) {
  return String(line || '')
    .replace(/^\s{0,3}#{1,4}\s+/, '')
    .replace(/^\s*[-*\u2022]\s+/, '')
    .replace(/^\s*\d+[.)]\s+/, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/[#*`_>]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

// Full cleaned, speakable text (multi-line -> single spoken string).
export function cleanForSpeech(text) {
  return String(text || '').split('\n').map(cleanLineForSpeech).filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
}

function splitWords(clean) {
  return clean ? clean.split(' ').filter(Boolean) : [];
}

/* --------------------------- shared playback --------------------------- */
let _audio = null;         // current HTMLAudioElement (Gemini path)
let _usingBrowser = false; // whether the browser synth is currently speaking
const _clip = new Map();   // "voice|chunk" -> playable data URL (client-side cache)
let _stopFlag = false;

export function stopAlbert() {
  _stopFlag = true;
  clearHLTimers();
  try { if (_audio) { _audio.pause(); _audio.src = ''; _audio = null; } } catch (e) { /* noop */ }
  try { if (typeof window !== 'undefined' && window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) { /* noop */ }
  _usingBrowser = false;
  endHL();
}

function notifyFallback(reason) {
  try {
    window.dispatchEvent(new CustomEvent('albert:voice-notice', {
      detail: { msg: "Albert's premium voice is resting — using the backup voice.", reason: reason || '' },
    }));
  } catch (e) { /* noop */ }
}

// Split text into speak-able chunks. The FIRST chunk is just one sentence so audio
// can start almost immediately; the rest are grouped (~220 chars) and prefetched
// while Albert is already talking.
function chunkText(text) {
  const sentences = (text.match(/[^.!?]+[.!?]+|\S[^.!?]*$/g) || [text])
    .map((s) => s.trim()).filter(Boolean);
  if (sentences.length <= 1) return [text];
  // First chunk is a single sentence so audio starts almost immediately. The
  // REST is grouped into large ~3000-char chunks to minimise the number of TTS
  // requests — Gemini TTS is metered per request, so fewer/larger calls make a
  // limited daily quota go much further (typically ~2 calls per read).
  const chunks = [sentences[0]];
  let buf = '';
  const MAX = 3000;
  for (let i = 1; i < sentences.length; i++) {
    if (buf && (buf + ' ' + sentences[i]).length > MAX) { chunks.push(buf); buf = sentences[i]; }
    else buf = (buf ? buf + ' ' : '') + sentences[i];
  }
  if (buf) chunks.push(buf);
  return chunks;
}

async function fetchTTS(chunk, tries = 3) {
  const pref = getVoicePref();
  const voice = pref.voice || 'Charon';
  const cacheKey = `${voice}|${chunk}`;
  if (_clip.has(cacheKey)) return _clip.get(cacheKey);
  let lastErr = null;
  for (let attempt = 0; attempt < tries; attempt++) {
    try {
      const res = await fetch(`${API_BASE}/v1/tts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: chunk, voice }),
      });
      if (res.status === 503) throw Object.assign(new Error('tts unavailable'), { fatal: true });
      if (!res.ok) throw new Error('tts http ' + res.status);
      const data = await res.json();
      if (!data || !data.audio_base64) throw new Error('no audio');
      const url = `data:${data.mime_type || 'audio/wav'};base64,${data.audio_base64}`;
      if (_clip.size > 60) _clip.clear();
      _clip.set(cacheKey, url);
      return url;
    } catch (e) {
      lastErr = e;
      if (e && e.fatal) break;
      // brief backoff before retrying (rate-limit friendly)
      if (attempt < tries - 1) await new Promise((r) => setTimeout(r, 350 * (attempt + 1)));
    }
  }
  throw lastErr || new Error('tts failed');
}

// Pre-generate (and cache) the audio for `text` so a later speakAlbert() plays instantly.
// Fire-and-forget; failures are ignored (Listen still works on demand).
export function prefetchAlbert(text) {
  try {
    if (getVoicePref().engine === 'browser') return; // nothing to prefetch for device voice
    const clean = cleanForSpeech(text);
    if (!clean) return;
    chunkText(clean).forEach((c) => { fetchTTS(c, 1).catch(() => {}); });
  } catch (e) { /* noop */ }
}

// Schedule proportional word highlights across one Gemini chunk's audio duration.
function scheduleChunkWords(baseIndex, chunkWords, durSec) {
  const dur = durSec && isFinite(durSec) && durSec > 0 ? durSec : Math.max(0.6, chunkWords.join(' ').length / 14);
  const totalChars = chunkWords.reduce((a, w) => a + w.length + 1, 0) || 1;
  let acc = 0;
  chunkWords.forEach((w, j) => {
    const t = (acc / totalChars) * dur * 1000;
    _hlTimers.push(setTimeout(() => { if (!_stopFlag) setWord(baseIndex + j); }, t));
    acc += w.length + 1;
  });
}

function playUrl(url, baseIndex, chunkWords, onStart) {
  return new Promise((resolve, reject) => {
    const audio = new Audio(url);
    _audio = audio;
    let scheduled = false;
    const doSchedule = () => {
      if (scheduled) return; scheduled = true;
      scheduleChunkWords(baseIndex, chunkWords, audio.duration);
    };
    audio.onplaying = () => { if (onStart) onStart(); doSchedule(); };
    audio.onended = () => resolve();
    audio.onerror = () => reject(new Error('play error'));
    const p = audio.play();
    if (p && p.catch) p.catch(reject);
  });
}

function browserSpeak(text, baseIndex, onStart, onEnd) {
  try {
    if (typeof window === 'undefined' || !window.speechSynthesis) { onEnd && onEnd(); return; }
    const synth = window.speechSynthesis;
    const uText = cleanForSpeech(text).slice(0, 4000);
    const uWords = splitWords(uText);
    const u = new SpeechSynthesisUtterance(uText);
    applyAlbertVoice(u, synth);
    u.onstart = () => { onStart && onStart(); };
    u.onboundary = (e) => {
      try {
        if (e.name && e.name !== 'word') return;
        const ci = e.charIndex || 0;
        let acc = 0; let idx = 0;
        for (let k = 0; k < uWords.length; k++) {
          if (ci < acc + uWords[k].length + 1) { idx = k; break; }
          acc += uWords[k].length + 1; idx = k;
        }
        if (!_stopFlag) setWord(baseIndex + idx);
      } catch (err) { /* noop */ }
    };
    u.onend = () => { _usingBrowser = false; endHL(); onEnd && onEnd(); };
    u.onerror = () => { _usingBrowser = false; endHL(); onEnd && onEnd(); };
    _usingBrowser = true;
    synth.cancel();
    synth.speak(u);
    setTimeout(() => { if (_usingBrowser) onStart && onStart(); }, 400);
  } catch (e) { _usingBrowser = false; endHL(); onEnd && onEnd(); }
}

// Speak `text` as Albert. Generates the first sentence fast to start quickly, and
// fires ALL remaining chunks in parallel so playback is gapless (no mid-text pause).
// Emits word-highlight events throughout. onStart fires when audio begins; onEnd when done.
export async function speakAlbert(text, { onStart, onEnd } = {}) {
  stopAlbert();
  _stopFlag = false;
  const clean = cleanForSpeech(text);
  if (!clean) { onEnd && onEnd(); return; }
  _hlText = clean;
  const allWords = splitWords(clean);
  const pref = getVoicePref();

  let started = false;
  const fireStart = () => { if (!started) { started = true; onStart && onStart(); } };
  const finish = () => { endHL(); onEnd && onEnd(); };

  // Device-voice path: skip Gemini entirely.
  if (pref.engine === 'browser') {
    browserSpeak(clean, 0, fireStart, finish);
    return;
  }

  const chunks = chunkText(clean);
  // Word offset (into allWords) at which each chunk begins.
  const chunkWordArr = chunks.map((c) => splitWords(c));
  const baseIdx = [];
  let running = 0;
  for (let i = 0; i < chunks.length; i++) { baseIdx.push(running); running += chunkWordArr[i].length; }

  // Kick off every chunk's generation at once so later chunks are ready in time.
  const jobs = chunks.map((c) => fetchTTS(c).catch(() => null));
  let fellBack = false;
  try {
    for (let i = 0; i < chunks.length; i++) {
      const url = await jobs[i];
      if (_stopFlag) return;
      if (!url) {
        if (!fellBack) { fellBack = true; notifyFallback('gen'); }
        clearHLTimers();
        browserSpeak(chunks.slice(i).join(' '), baseIdx[i], started ? null : fireStart, finish);
        return;
      }
      try {
        clearHLTimers();
        await playUrl(url, baseIdx[i], chunkWordArr[i], fireStart);
      } catch (e) {
        if (!fellBack) { fellBack = true; notifyFallback('play'); }
        clearHLTimers();
        browserSpeak(chunks.slice(i).join(' '), baseIdx[i], started ? null : fireStart, finish);
        return;
      }
      if (_stopFlag) return;
    }
    finish();
  } catch (e) {
    notifyFallback('error');
    browserSpeak(clean, 0, onStart, finish);
  }
}

// Quick sample used by the voice picker's "Play sample" button. Respects a
// temporary voice override so the user can preview before saving.
export function previewVoice(sample, override) {
  const prev = getVoicePref();
  try {
    if (override) {
      try { localStorage.setItem(PREF_KEY, JSON.stringify({ ...prev, ...override })); } catch (e) { /* noop */ }
      _clip.clear();
    }
    return new Promise((resolve) => {
      speakAlbert(sample || "Hello! I'm Albert, your crypto quant. Let's read the market together.", {
        onEnd: () => {
          if (override) { try { localStorage.setItem(PREF_KEY, JSON.stringify(prev)); } catch (e) { /* noop */ } _clip.clear(); }
          resolve();
        },
      });
    });
  } catch (e) {
    if (override) { try { localStorage.setItem(PREF_KEY, JSON.stringify(prev)); } catch (er) { /* noop */ } }
    return Promise.resolve();
  }
}
