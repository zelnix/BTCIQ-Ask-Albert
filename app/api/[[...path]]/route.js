import { NextResponse } from 'next/server';

// Internal FastAPI ML microservice (managed by supervisor on :8001).
const FASTAPI_URL = process.env.FASTAPI_INTERNAL_URL || 'http://localhost:8001';

async function proxy(request, context) {
  const resolved = await context.params;
  const parts = resolved?.path || [];
  const path = Array.isArray(parts) ? parts.join('/') : String(parts || '');
  const url = new URL(request.url);
  const target = `${FASTAPI_URL}/api/${path}${url.search}`;

  const init = {
    method: request.method,
    headers: { 'content-type': request.headers.get('content-type') || 'application/json' },
  };
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
    return NextResponse.json(
      { status: 'error', error: 'ML backend unavailable: ' + String(e) },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
export const dynamic = 'force-dynamic';
