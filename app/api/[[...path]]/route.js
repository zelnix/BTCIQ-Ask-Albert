import { NextResponse } from 'next/server';
import { ensureBackend } from '@/lib/backend-supervisor';

// Internal FastAPI ML microservice (managed by supervisor on :8001).
const FASTAPI_URL = process.env.FASTAPI_INTERNAL_URL || 'http://localhost:8001';

// Upstream timeout. Long enough for the heavier ML endpoints, short enough that a
// wedged backend cannot hold a Next.js worker open indefinitely.
const TIMEOUT_MS = Number(process.env.FASTAPI_TIMEOUT_MS || 45000);

// Turn a fetch() failure into an explicit (status, code) pair so callers and logs can
// tell "backend is not running" apart from "backend is slow" apart from "edge 502".
function classify(err) {
  if (err && (err.name === 'AbortError' || err.name === 'TimeoutError')) {
    return {
      status: 504,
      code: 'backend_timeout',
      message: 'upstream did not respond within ' + TIMEOUT_MS + 'ms',
    };
  }
  const cause = (err && err.cause) || {};
  const sys = cause.code || (err && err.code) || '';
  if (sys === 'ECONNREFUSED' || sys === 'ENOTFOUND' || sys === 'EAI_AGAIN') {
    return {
      status: 503,
      code: 'backend_unavailable',
      message: 'nothing is listening on ' + FASTAPI_URL + ' (' + sys + ')',
    };
  }
  if (sys === 'ECONNRESET' || sys === 'EPIPE') {
    return {
      status: 502,
      code: 'backend_reset',
      message: 'upstream closed the connection (' + sys + ')',
    };
  }
  return { status: 502, code: 'backend_error', message: String(err) };
}

async function proxy(request, context) {
  // Make sure the FastAPI service on :8001 is actually running. This is a no-op
  // after the first call and when something is already listening, and it is
  // fire-and-forget so it never adds latency to the request.
  ensureBackend().catch(() => {});

  const resolved = await context.params;
  const parts = resolved?.path || [];
  const path = Array.isArray(parts) ? parts.join('/') : String(parts || '');
  const url = new URL(request.url);
  const target = `${FASTAPI_URL}/api/${path}${url.search}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  const init = {
    method: request.method,
    headers: { 'content-type': request.headers.get('content-type') || 'application/json' },
    signal: controller.signal,
  };

  // Forward the real client IP so the FastAPI per-client rate limiter buckets by
  // actual user (not 127.0.0.1). Without this, one user's limit would block everyone.
  const fwd = request.headers.get('x-forwarded-for');
  const realIp = request.headers.get('x-real-ip');
  if (fwd) init.headers['x-forwarded-for'] = fwd;
  else if (realIp) init.headers['x-forwarded-for'] = realIp;
  if (realIp) init.headers['x-real-ip'] = realIp;

  if (!['GET', 'HEAD'].includes(request.method)) {
    init.body = await request.text();
  }

  try {
    const res = await fetch(target, init);
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { 'content-type': res.headers.get('content-type') || 'application/json' },
    });
  } catch (e) {
    const { status, code, message } = classify(e);
    console.error('[api-proxy] ' + request.method + ' ' + target + ' -> ' + code + ': ' + message);
    return NextResponse.json(
      {
        status: 'error',
        code,
        error: 'ML backend unavailable: ' + message,
        upstream: FASTAPI_URL,
      },
      { status },
    );
  } finally {
    clearTimeout(timer);
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
