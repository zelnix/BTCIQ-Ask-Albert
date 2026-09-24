'use client';
// Shared, persisted Ask-Albert chat store.
//
// One conversation per user (pid). The floating widget AND the full "Ask Albert"
// section both use useAlbertChat(pid), so they share the SAME messages and stay
// in sync live. History is loaded from / saved to the backend
// (GET/PUT/POST /api/v1/albert/chat*) so it survives navigation, expand, reloads
// and follows the user across devices.
import React from 'react';
import { API_BASE } from './api';

const _cache = {};        // pid -> { sessionId, messages, loaded, dirty }
const _loading = {};      // pid -> Promise (dedupe concurrent loads)
const _saveTimers = {};   // pid -> debounce timeout

function newSid() {
  return (typeof crypto !== 'undefined' && crypto.randomUUID)
    ? crypto.randomUUID().replace(/-/g, '')
    : String(Math.random()).slice(2) + String(Date.now());
}

function _emit(pid) {
  try { window.dispatchEvent(new CustomEvent('albert:chat', { detail: { pid } })); } catch (e) { /* noop */ }
}

async function _loadFromServer(pid) {
  try {
    const r = await fetch(`${API_BASE}/v1/albert/chat?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' });
    const j = await r.json();
    return {
      sessionId: j.sessionId || newSid(),
      messages: Array.isArray(j.messages) ? j.messages : [],
    };
  } catch (e) {
    return { sessionId: newSid(), messages: [] };
  }
}

function _scheduleSave(pid) {
  clearTimeout(_saveTimers[pid]);
  _saveTimers[pid] = setTimeout(() => {
    const c = _cache[pid];
    if (!c) return;
    fetch(`${API_BASE}/v1/albert/chat`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pid, sessionId: c.sessionId, messages: (c.messages || []).slice(-200) }),
    }).catch(() => { /* noop — will retry on next change */ });
  }, 600);
}

export function useAlbertChat(pid) {
  const [, force] = React.useReducer((x) => x + 1, 0);
  const [ready, setReady] = React.useState(Boolean(_cache[pid] && _cache[pid].loaded));

  React.useEffect(() => {
    if (!pid) return undefined;
    let alive = true;

    if (!_cache[pid]) {
      // Seed an empty conversation immediately so the UI is usable while we load.
      _cache[pid] = { sessionId: newSid(), messages: [], loaded: false, dirty: false };
    }

    if (!_cache[pid].loaded && !_loading[pid]) {
      _loading[pid] = _loadFromServer(pid).then((data) => {
        const c = _cache[pid];
        // Only adopt server history if the user hasn't already started typing
        // locally (avoid clobbering an in-flight message).
        if (c && !c.dirty && (c.messages || []).length === 0) {
          _cache[pid] = { ...data, loaded: true, dirty: false };
        } else if (c) {
          c.loaded = true;
        }
        _loading[pid] = null;
        _emit(pid);
      });
    }

    const onEvt = (e) => {
      if (!alive) return;
      if (!e.detail || e.detail.pid === pid) {
        setReady(Boolean(_cache[pid] && _cache[pid].loaded));
        force();
      }
    };
    window.addEventListener('albert:chat', onEvt);
    // Reflect current state on (re)mount.
    setReady(Boolean(_cache[pid] && _cache[pid].loaded));
    return () => { alive = false; window.removeEventListener('albert:chat', onEvt); };
  }, [pid]);

  const messages = (_cache[pid] && _cache[pid].messages) || [];
  const sessionId = (_cache[pid] && _cache[pid].sessionId) || '';

  const setMessages = React.useCallback((updater) => {
    if (!pid) return;
    const c = _cache[pid] || (_cache[pid] = { sessionId: newSid(), messages: [], loaded: true, dirty: false });
    c.messages = typeof updater === 'function' ? updater(c.messages || []) : updater;
    c.dirty = true;
    _emit(pid);
    _scheduleSave(pid);
  }, [pid]);

  const clear = React.useCallback(() => {
    if (!pid) return;
    const sid = newSid();
    _cache[pid] = { sessionId: sid, messages: [], loaded: true, dirty: false };
    _emit(pid);
    clearTimeout(_saveTimers[pid]);
    fetch(`${API_BASE}/v1/albert/chat/clear`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pid, sessionId: sid }),
    }).catch(() => { /* noop */ });
  }, [pid]);

  return { messages, setMessages, sessionId, clear, ready };
}

// Plain-text export of a conversation for the "Copy" button.
export function chatToText(messages) {
  return (messages || [])
    .filter((m) => m && (m.text || '').trim())
    .map((m) => `${m.role === 'user' ? 'You' : 'Albert'}: ${m.text}`)
    .join('\n\n');
}
