'use client';
// Shared, persisted, MULTI-THREAD Ask-Albert chat store.
//
// One user (pid) can have many named conversation threads. The floating widget
// AND the full "Ask Albert" section both use useAlbertChat(pid), so they share
// the SAME active thread + thread list and stay in sync live. Everything is
// persisted to the backend (/api/v1/albert/chat*) so it follows the user across
// devices. Threads auto-title from the first message.
import React from 'react';
import { API_BASE } from './api';

const _cache = {};        // pid -> { threads, activeId, byId, threadsLoaded }
const _saveTimers = {};   // tid -> debounce timeout

function newSid() {
  return (typeof crypto !== 'undefined' && crypto.randomUUID)
    ? crypto.randomUUID().replace(/-/g, '')
    : String(Math.random()).slice(2) + String(Date.now());
}
function _emit(pid) { try { window.dispatchEvent(new CustomEvent('albert:chat', { detail: { pid } })); } catch (e) { /* noop */ } }
function _activeKey(pid) { return `albert_active_thread_${pid}`; }
function _titleFrom(messages) {
  const u = (messages || []).find((m) => m.role === 'user' && (m.text || '').trim());
  if (!u) return 'New chat';
  const t = u.text.replace(/\s+/g, ' ').trim();
  return t.length > 48 ? t.slice(0, 48) + '…' : t;
}
function _ensure(pid) {
  if (!_cache[pid]) _cache[pid] = { threads: [], activeId: null, byId: {}, threadsLoaded: false };
  return _cache[pid];
}

async function _get(url) { try { return await (await fetch(url, { cache: 'no-store' })).json(); } catch (e) { return null; } }
function _post(url, body) { return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).catch(() => {}); }

function _scheduleSave(pid, tid) {
  clearTimeout(_saveTimers[tid]);
  _saveTimers[tid] = setTimeout(() => {
    const c = _cache[pid]; const t = c && c.byId[tid];
    if (!t) return;
    fetch(`${API_BASE}/v1/albert/chat`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pid, threadId: tid, sessionId: t.sessionId, title: t.title, messages: (t.messages || []).slice(-200) }),
    }).catch(() => {});
  }, 600);
}

async function _loadThread(pid, tid) {
  const c = _ensure(pid);
  if (c.byId[tid] && c.byId[tid].loaded) return;
  const j = await _get(`${API_BASE}/v1/albert/chat?pid=${encodeURIComponent(pid)}&threadId=${encodeURIComponent(tid)}`);
  if (j && j.status === 'ready') {
    const cur = c.byId[tid];
    if (cur && cur.dirty && (cur.messages || []).length) { cur.loaded = true; }
    else c.byId[tid] = { sessionId: j.sessionId, title: j.title || 'New chat', messages: j.messages || [], loaded: true, dirty: false };
    _emit(pid);
  }
}

async function _init(pid) {
  const c = _ensure(pid);
  if (c.threadsLoaded) return;
  const j = await _get(`${API_BASE}/v1/albert/chat/threads?pid=${encodeURIComponent(pid)}`);
  c.threads = (j && j.threads) || [];
  c.threadsLoaded = true;
  let active = null;
  try { active = window.localStorage.getItem(_activeKey(pid)); } catch (e) { /* noop */ }
  if (!active || !c.threads.find((t) => t.threadId === active)) {
    active = c.threads.length ? c.threads[0].threadId : newSid();
  }
  c.activeId = active;
  if (!c.byId[active]) c.byId[active] = { sessionId: newSid(), title: 'New chat', messages: [], loaded: false, dirty: false };
  _emit(pid);
  if (c.threads.find((t) => t.threadId === active)) await _loadThread(pid, active);
  else { c.byId[active].loaded = true; _emit(pid); }
}

export function useAlbertChat(pid) {
  const [, force] = React.useReducer((x) => x + 1, 0);

  React.useEffect(() => {
    if (!pid) return undefined;
    _init(pid);
    const onEvt = (e) => { if (!e.detail || e.detail.pid === pid) force(); };
    window.addEventListener('albert:chat', onEvt);
    return () => window.removeEventListener('albert:chat', onEvt);
  }, [pid]);

  const c = _cache[pid] || { threads: [], activeId: null, byId: {}, threadsLoaded: false };
  const activeId = c.activeId;
  const active = (activeId && c.byId[activeId]) || { sessionId: '', title: 'New chat', messages: [], loaded: false };

  const setMessages = React.useCallback((updater) => {
    if (!pid) return;
    const cc = _ensure(pid);
    const tid = cc.activeId;
    const t = cc.byId[tid] || (cc.byId[tid] = { sessionId: newSid(), title: 'New chat', messages: [], loaded: true, dirty: false });
    t.messages = typeof updater === 'function' ? updater(t.messages || []) : updater;
    t.dirty = true;
    if (!t.title || t.title === 'New chat') t.title = _titleFrom(t.messages);
    const now = new Date().toISOString();
    const existing = cc.threads.find((x) => x.threadId === tid);
    if (existing) { existing.title = t.title; existing.updatedAt = now; existing.count = t.messages.length; }
    else cc.threads.unshift({ threadId: tid, title: t.title, updatedAt: now, count: t.messages.length });
    cc.threads.sort((a, b) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')));
    _emit(pid); _scheduleSave(pid, tid);
  }, [pid]);

  const switchThread = React.useCallback((tid) => {
    if (!pid || !tid) return;
    const cc = _ensure(pid);
    cc.activeId = tid;
    try { window.localStorage.setItem(_activeKey(pid), tid); } catch (e) { /* noop */ }
    if (!cc.byId[tid]) cc.byId[tid] = { sessionId: newSid(), title: 'New chat', messages: [], loaded: false, dirty: false };
    _emit(pid);
    if (!cc.byId[tid].loaded) _loadThread(pid, tid);
  }, [pid]);

  const newThread = React.useCallback(() => {
    if (!pid) return;
    const cc = _ensure(pid);
    const tid = newSid();
    cc.byId[tid] = { sessionId: newSid(), title: 'New chat', messages: [], loaded: true, dirty: false };
    cc.activeId = tid;
    try { window.localStorage.setItem(_activeKey(pid), tid); } catch (e) { /* noop */ }
    _emit(pid);
  }, [pid]);

  const renameThread = React.useCallback((tid, title) => {
    if (!pid || !tid) return;
    const cc = _ensure(pid);
    const clean = (title || '').trim().slice(0, 80) || 'New chat';
    if (cc.byId[tid]) cc.byId[tid].title = clean;
    const th = cc.threads.find((x) => x.threadId === tid); if (th) th.title = clean;
    _emit(pid);
    _post(`${API_BASE}/v1/albert/chat/rename`, { pid, threadId: tid, title: clean });
  }, [pid]);

  const deleteThread = React.useCallback((tid) => {
    if (!pid || !tid) return;
    const cc = _ensure(pid);
    cc.threads = cc.threads.filter((x) => x.threadId !== tid);
    delete cc.byId[tid];
    if (cc.activeId === tid) {
      cc.activeId = cc.threads.length ? cc.threads[0].threadId : newSid();
      try { window.localStorage.setItem(_activeKey(pid), cc.activeId); } catch (e) { /* noop */ }
      if (!cc.byId[cc.activeId]) cc.byId[cc.activeId] = { sessionId: newSid(), title: 'New chat', messages: [], loaded: false, dirty: false };
      if (cc.threads.find((t) => t.threadId === cc.activeId) && !cc.byId[cc.activeId].loaded) _loadThread(pid, cc.activeId);
      else cc.byId[cc.activeId].loaded = true;
    }
    _emit(pid);
    _post(`${API_BASE}/v1/albert/chat/delete`, { pid, threadId: tid });
  }, [pid]);

  return {
    messages: active.messages || [],
    setMessages,
    sessionId: active.sessionId || '',
    threadId: activeId,
    title: active.title || 'New chat',
    threads: c.threads || [],
    ready: Boolean(active.loaded),
    switchThread, newThread, renameThread, deleteThread,
    clear: newThread,
  };
}

export function chatToText(messages) {
  return (messages || [])
    .filter((m) => m && (m.text || '').trim())
    .map((m) => `${m.role === 'user' ? 'You' : 'Albert'}: ${m.text}`)
    .join('\n\n');
}

export async function downloadChatPdf(messages, title = 'Ask Albert conversation') {
  const rows = (messages || []).filter((m) => m && (m.text || '').trim());
  if (!rows.length) return;
  const { jsPDF } = await import('jspdf');
  const doc = new jsPDF({ unit: 'pt', format: 'a4' });
  const margin = 48;
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const maxW = pageW - margin * 2;
  let y = margin;
  doc.setFont('helvetica', 'bold'); doc.setFontSize(16); doc.setTextColor(20);
  doc.text('Ask Albert', margin, y); y += 20;
  doc.setFont('helvetica', 'normal'); doc.setFontSize(10); doc.setTextColor(120);
  doc.text(new Date().toLocaleString(), margin, y); y += 22;
  rows.forEach((m) => {
    const who = m.role === 'user' ? 'You' : 'Albert';
    if (y > pageH - margin) { doc.addPage(); y = margin; }
    doc.setFont('helvetica', 'bold'); doc.setFontSize(11);
    doc.setTextColor(m.role === 'user' ? 30 : 12, m.role === 'user' ? 100 : 90, m.role === 'user' ? 160 : 140);
    doc.text(who, margin, y); y += 15;
    doc.setFont('helvetica', 'normal'); doc.setFontSize(11); doc.setTextColor(40);
    doc.splitTextToSize(String(m.text || ''), maxW).forEach((ln) => {
      if (y > pageH - margin) { doc.addPage(); y = margin; }
      doc.text(ln, margin, y); y += 15;
    });
    y += 10;
  });
  const safe = (title || 'ask-albert').replace(/[^a-z0-9]+/gi, '-').toLowerCase().slice(0, 40);
  doc.save(`${safe || 'ask-albert'}.pdf`);
}
