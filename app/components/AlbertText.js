'use client';

import React from 'react';
import { onAlbertHighlight, cleanForSpeech } from '../lib/albertVoice';

// Turn a content string (which may contain **bold**) into ordered words with a
// bold flag. The word order matches cleanForSpeech(), so global indices line up
// with the karaoke highlight events emitted while Albert reads.
function contentWords(content) {
  const out = [];
  const re = /\*\*(.+?)\*\*/g;
  let last = 0; let m;
  const pushPlain = (s, bold) => { s.split(/\s+/).filter(Boolean).forEach((w) => out.push({ word: w, bold })); };
  while ((m = re.exec(content)) !== null) {
    if (m.index > last) pushPlain(content.slice(last, m.index), false);
    pushPlain(m[1], true);
    last = m.index + m[0].length;
  }
  if (last < content.length) pushPlain(content.slice(last), false);
  return out;
}

// Lightweight markdown-ish renderer for Albert chat replies with karaoke-style
// word highlighting synced to his voice.
export default function AlbertText({ text }) {
  const clean = React.useMemo(() => cleanForSpeech(text), [text]);
  const [active, setActive] = React.useState(-1);
  const wrapRef = React.useRef(null);

  React.useEffect(() => {
    const off = onAlbertHighlight(({ text: t, index, active: on }) => {
      if (on && t && t === clean) setActive(index);
      else setActive(-1);
    });
    return off;
  }, [clean]);

  // Keep the highlighted word visible during a read.
  React.useEffect(() => {
    if (active < 0 || !wrapRef.current) return;
    const el = wrapRef.current.querySelector('[data-hl="on"]');
    try { el && el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch (e) { /* noop */ }
  }, [active]);

  // Running global word counter shared across all lines (matches cleanForSpeech order).
  let wi = 0;
  const renderContent = (content) => {
    const words = contentWords(content);
    return words.map((w, k) => {
      const idx = wi++;
      const on = idx === active;
      return (
        <span key={k} data-hl={on ? 'on' : undefined}
          className={`${w.bold ? 'font-semibold text-white' : ''} ${on ? 'rounded bg-amber-400/30 text-white shadow-[0_0_0_1px_rgba(251,191,36,0.35)]' : ''}`}>
          {w.word}{k < words.length - 1 ? ' ' : ''}
        </span>
      );
    });
  };

  const lines = String(text || '').split('\n');
  const out = [];
  lines.forEach((raw, i) => {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) { out.push(<div key={i} className="h-1.5" />); return; }
    const h = line.match(/^\s{0,3}(#{1,4})\s+(.*)$/);
    if (h) {
      out.push(<p key={i} className="mt-2 mb-0.5 text-[13px] font-bold text-white">{renderContent(h[2].replace(/:+$/, ''))}</p>);
      return;
    }
    const b = line.match(/^\s*[-*\u2022]\s+(.*)$/);
    if (b) {
      out.push(
        <div key={i} className="flex gap-1.5">
          <span className="mt-0.5 shrink-0 text-sky-400">{'\u2022'}</span>
          <span className="flex-1">{renderContent(b[1])}</span>
        </div>,
      );
      return;
    }
    const n = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    if (n) {
      out.push(
        <div key={i} className="flex gap-1.5">
          <span className="shrink-0 font-semibold text-sky-300">{n[1]}.</span>
          <span className="flex-1">{renderContent(n[2])}</span>
        </div>,
      );
      return;
    }
    out.push(<p key={i}>{renderContent(line)}</p>);
  });
  return <div ref={wrapRef} className="space-y-1">{out}</div>;
}
