import { diagnosticsResponse } from '@/lib/diagnostics';

// Convenience alias for local/preview use. In production the platform reserves
// /healthz and answers it at the edge, so use /app-status there instead.
export const dynamic = 'force-dynamic';

export async function GET() {
  return diagnosticsResponse();
}
