// Single source of truth for the API prefix used by every call in the app.
// The deployed edge routes /api/* to the FastAPI backend origin; if that prefix
// ever moves, change it here (or set NEXT_PUBLIC_API_BASE at build time).
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api';

// Global "reading level" preference: 'simple' (plain English, default) or 'pro' (technical).
export function getReadingLevel() {
  if (typeof window === 'undefined') return 'simple';
  try { return window.localStorage.getItem('btciq_reading_level') || 'simple'; } catch (e) { return 'simple'; }
}
export function setReadingLevel(v) {
  try {
    window.localStorage.setItem('btciq_reading_level', v);
    window.dispatchEvent(new CustomEvent('albert:reading-level', { detail: v }));
  } catch (e) { /* noop */ }
}

// Stable per-device client id used to persist the user's portfolio server-side
// and to scope their price-alert watches.
export function getPid() {
  if (typeof window === 'undefined') return '';
  try {
    // When signed in, scope all per-user data (portfolio, watchlist, strategies)
    // to the authenticated user id. Falls back to a stable per-device id otherwise.
    const uid = window.localStorage.getItem('btciq_user_id');
    if (uid) return 'u_' + uid;
    let pid = window.localStorage.getItem('btciq_pid');
    if (!pid) {
      pid = 'pid_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
      window.localStorage.setItem('btciq_pid', pid);
    }
    return pid;
  } catch (e) {
    return '';
  }
}

