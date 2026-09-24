'use client';
// Tiny copy-to-clipboard button with a brief "copied" checkmark. Used for
// per-message copy in the Ask-Albert chats.
import React from 'react';
import { Copy, Check } from 'lucide-react';

export default function CopyButton({ text, className = '', title = 'Copy message', size = 12 }) {
  const [copied, setCopied] = React.useState(false);
  const onCopy = (e) => {
    e.stopPropagation();
    const t = (text || '').trim();
    if (!t) return;
    try {
      navigator.clipboard.writeText(t);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (err) { /* noop */ }
  };
  return (
    <button
      type="button"
      onClick={onCopy}
      title={title}
      className={`rounded p-1 text-slate-400 transition-colors hover:text-slate-100 ${className}`}
    >
      {copied
        ? <Check style={{ width: size, height: size }} className="text-emerald-400" />
        : <Copy style={{ width: size, height: size }} />}
    </button>
  );
}
