'use client';

import React from 'react';

// Parse **bold** spans within a single line of Albert's reply.
function renderInline(text) {
  const parts = [];
  const regex = /\*\*(.+?)\*\*/g;
  let last = 0;
  let m;
  let key = 0;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push(<strong key={key++} className="font-semibold text-white">{m[1]}</strong>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

// Lightweight markdown-ish renderer for Albert chat replies: headings (#),
// bullets (-, *, •), numbered lists and **bold**. Keeps things readable without
// pulling in a full markdown dependency.
export default function AlbertText({ text }) {
  const lines = String(text || '').split('\n');
  const out = [];
  lines.forEach((raw, i) => {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) { out.push(<div key={i} className="h-1.5" />); return; }
    const h = line.match(/^\s{0,3}(#{1,4})\s+(.*)$/);
    if (h) {
      out.push(<p key={i} className="mt-2 mb-0.5 text-[13px] font-bold text-white">{renderInline(h[2].replace(/:+$/, ''))}</p>);
      return;
    }
    const b = line.match(/^\s*[-*•]\s+(.*)$/);
    if (b) {
      out.push(
        <div key={i} className="flex gap-1.5">
          <span className="mt-0.5 shrink-0 text-sky-400">•</span>
          <span className="flex-1">{renderInline(b[1])}</span>
        </div>,
      );
      return;
    }
    const n = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    if (n) {
      out.push(
        <div key={i} className="flex gap-1.5">
          <span className="shrink-0 font-semibold text-sky-300">{n[1]}.</span>
          <span className="flex-1">{renderInline(n[2])}</span>
        </div>,
      );
      return;
    }
    out.push(<p key={i}>{renderInline(line)}</p>);
  });
  return <div className="space-y-1">{out}</div>;
}
