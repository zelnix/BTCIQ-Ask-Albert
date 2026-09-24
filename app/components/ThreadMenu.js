'use client';
// Thread switcher for the Ask-Albert chats — pick a saved conversation, start a
// new one, rename or delete. Shared by the floating widget and the full section.
import React from 'react';
import { MessagesSquare, Plus, Check, Pencil, Trash2, ChevronDown } from 'lucide-react';

export default function ThreadMenu({ threads = [], activeId, title, onSwitch, onNew, onRename, onDelete, compact = false }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);
  React.useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);
  const doRename = (t) => {
    const v = window.prompt('Rename this chat', t.title || 'New chat');
    if (v != null) onRename && onRename(t.threadId, v);
  };
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((v) => !v)} title="Your chats"
        className={`flex items-center gap-1 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-white ${compact ? 'p-1.5' : 'px-2 py-1 text-[11px] font-semibold'}`}>
        <MessagesSquare className="h-3.5 w-3.5" />
        {!compact && <span className="max-w-[120px] truncate">{title || 'New chat'}</span>}
        <ChevronDown className="h-3 w-3" />
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-1 max-h-72 w-64 overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-1 shadow-2xl">
          <button onClick={() => { onNew && onNew(); setOpen(false); }}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-[12px] font-semibold text-sky-300 hover:bg-slate-800">
            <Plus className="h-3.5 w-3.5" />New chat
          </button>
          <div className="my-1 border-t border-slate-800" />
          {threads.length === 0 && <p className="px-2.5 py-2 text-[11px] text-slate-500">No saved chats yet.</p>}
          {threads.map((t) => (
            <div key={t.threadId} className={`group flex items-center gap-1 rounded-lg px-2 py-1.5 text-[12px] hover:bg-slate-800 ${t.threadId === activeId ? 'bg-slate-800/70' : ''}`}>
              <button onClick={() => { onSwitch && onSwitch(t.threadId); setOpen(false); }} className="flex min-w-0 flex-1 items-center gap-1.5 text-left text-slate-200">
                {t.threadId === activeId ? <Check className="h-3.5 w-3.5 shrink-0 text-emerald-400" /> : <span className="h-3.5 w-3.5 shrink-0" />}
                <span className="truncate">{t.title || 'New chat'}</span>
              </button>
              <button onClick={() => doRename(t)} title="Rename" className="shrink-0 p-1 text-slate-500 opacity-0 hover:text-slate-200 group-hover:opacity-100"><Pencil className="h-3 w-3" /></button>
              <button onClick={() => { if (window.confirm('Delete this chat?')) onDelete && onDelete(t.threadId); }} title="Delete" className="shrink-0 p-1 text-slate-500 opacity-0 hover:text-rose-300 group-hover:opacity-100"><Trash2 className="h-3 w-3" /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
