// Albert's voice profile — a warm, well-aged scientific professor who is cool,
// hip and unhurried. Uses the browser's native SpeechSynthesis, so no API key.
// We pick the richest, most mature male English voice available on the device
// and tune rate/pitch for a measured, characterful delivery.

// Ranked by how "seasoned professor + smooth" they sound across platforms.
// (macOS: Daniel/Alex/Oliver/Rishi · Windows: Guy/Davis/George/Ryan ·
//  Android/Chrome: Google UK English Male · generic: any male/en voice.)
const PREF = [
  /daniel/i,               // UK, warm baritone (macOS/iOS) — the signature Albert
  /arthur|oliver|rishi/i,  // other rich UK male voices
  /google uk english male/i,
  /(guy|davis|george|ryan|christopher|eric|brian|tony).*natural/i, // MS Neural males
  /microsoft (guy|davis|george|ryan|mark)/i,
  /alex\b/i,               // macOS rich male
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
  // Last resort: prefer any "natural/neural" english voice, else the first english one.
  return pool.find((v) => /natural|neural|enhanced|premium/i.test(v.name || '')) || pool[0] || null;
}

// Apply Albert's persona to an utterance: seasoned, warm, unhurried.
export function applyAlbertVoice(u, synth) {
  try {
    const v = pickAlbertVoice(synth);
    if (v) u.voice = v;
  } catch (e) { /* noop */ }
  u.rate = 0.93;   // measured, thoughtful — not sluggish
  u.pitch = 0.88;  // deeper, well-aged, warm
  u.volume = 1;
  return u;
}
