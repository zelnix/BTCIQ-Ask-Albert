import { diagnosticsResponse } from '@/lib/diagnostics';

// Canonical deployment diagnostic endpoint.
// /healthz is reserved by the hosting platform in production (it answers with a plain
// "." before the request ever reaches this app), so the real diagnostics live here.
export const dynamic = 'force-dynamic';

export async function GET() {
  return diagnosticsResponse();
}
