// Single source of truth for the API prefix used by every call in the app.
// The deployed edge routes /api/* to the FastAPI backend origin; if that prefix
// ever moves, change it here (or set NEXT_PUBLIC_API_BASE at build time).
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api';

// Stable per-device client id used to persist the user's portfolio server-side
// and to scope their price-alert watches.
export function getPid() {
  if (typeof window === 'undefined') return '';
  try {
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

