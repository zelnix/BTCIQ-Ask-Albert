import { NextResponse } from 'next/server';
import fs from 'fs';
import { backendCandidates, resolveBackendDir, backendCwd } from './backend-paths';

// Deployment diagnostics, served by Next.js itself so it is reachable even when the
// FastAPI backend on :8001 is missing. Exposed at /app-status (and /healthz in
// environments where the platform has not already reserved that path).
//
// IMPORTANT: this endpoint reports only environment variable NAMES and a present /
// absent boolean. It never reads, logs or returns a value.

const FASTAPI_URL = process.env.FASTAPI_INTERNAL_URL || 'http://localhost:8001';
const PROBE_TIMEOUT_MS = Number(process.env.HEALTHZ_TIMEOUT_MS || 5000);

const REQUIRED_ENV = [
  'MONGO_URL',
  'DB_NAME',
  'CORS_ORIGINS',
  'NEXT_PUBLIC_BASE_URL',
  'EMERGENT_LLM_KEY',
  'ADMIN_PASSCODE',
  'GLASSNODE_API_KEY',
  'COINGLASS_API_KEY',
  'FRED_API_KEY',
];

// If none of these exist in the image, the container physically cannot run the
// FastAPI backend no matter what environment variables are injected.
const PY_CANDIDATES = [
  '/root/.venv/bin/python',
  '/root/.venv/bin/uvicorn',
  '/usr/local/bin/python3',
  '/usr/local/bin/uvicorn',
  '/usr/bin/python3',
  '/usr/bin/uvicorn',
];

function exists(p) {
  try {
    return fs.existsSync(p);
  } catch {
    return false;
  }
}

async function probeBackend() {
  const started = Date.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    // Any HTTP response (even 404) proves a process is listening on :8001.
    const res = await fetch(FASTAPI_URL + '/api/', { signal: controller.signal, cache: 'no-store' });
    return { reachable: true, http_status: res.status, latency_ms: Date.now() - started, error: null };
  } catch (e) {
    const cause = (e && e.cause) || {};
    return {
      reachable: false,
      http_status: null,
      latency_ms: Date.now() - started,
      error: cause.code || (e && e.name) || 'unknown',
    };
  } finally {
    clearTimeout(timer);
  }
}

export async function diagnostics() {
  const backend = await probeBackend();

  const env_present = {};
  let missing = 0;
  for (const k of REQUIRED_ENV) {
    const ok = Boolean(process.env[k] && String(process.env[k]).length > 0);
    env_present[k] = ok;
    if (!ok) missing += 1;
  }

  const python_runtime = PY_CANDIDATES.filter(exists);
  const backend_candidates = backendCandidates();
  const backend_dir = resolveBackendDir();
  const backend_source_present = Boolean(backend_dir);
  const cwd = backendCwd();

  let diagnosis;
  if (backend.reachable) {
    diagnosis = 'Next.js and the FastAPI backend are both up.';
  } else if (!backend_source_present) {
    diagnosis =
      'The FastAPI backend source (backend/server.py) is NOT present in this image - ' +
      'searched ' + backend_candidates.map((c) => c.dir).join(', ') +
      ' from cwd ' + cwd + '. The build only ships the Next.js app, so the backend ' +
      'can never start here. This is a BUILD/TEMPLATE problem, not a secrets ' +
      'problem: injecting environment variables will not fix it.';
  } else if (backend_source_present && python_runtime.length === 0) {
    diagnosis =
      'The backend source ships in this image but there is no Python/uvicorn runtime in it, ' +
      'so the FastAPI service cannot start here. This is a BUILD/TEMPLATE problem, not a ' +
      'secrets problem: injecting environment variables will not fix it.';
  } else if (missing > 0) {
    diagnosis =
      'Python runtime is present but ' + missing + ' required environment variable(s) are ' +
      'absent, and nothing is listening on :8001.';
  } else {
    diagnosis =
      'Python runtime and all required environment variables are present, but nothing is ' +
      'listening on :8001 - the backend process is not being started by the container.';
  }

  return {
    ok: backend.reachable,
    service: 'nextjs',
    served_by: 'next-app-router',
    time: new Date().toISOString(),
    backend: { url: FASTAPI_URL, source_present: backend_source_present, ...backend },
    cwd,
    backend_dir,
    backend_candidates,
    python_runtime,
    env_present,
    env_missing_count: missing,
    diagnosis,
  };
}

export async function diagnosticsResponse() {
  const body = await diagnostics();
  return NextResponse.json(body, {
    status: body.ok ? 200 : 503,
    headers: { 'cache-control': 'no-store' },
  });
}
