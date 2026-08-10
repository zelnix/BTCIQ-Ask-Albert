// Single source of truth for the API prefix used by every call in the app.
// The deployed edge routes /api/* to the FastAPI backend origin; if that prefix
// ever moves, change it here (or set NEXT_PUBLIC_API_BASE at build time).
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api';
