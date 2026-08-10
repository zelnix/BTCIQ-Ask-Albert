// Resolves where the FastAPI backend source actually lives.
// The preview container uses /app, but a deployed image may use a different
// working directory, so never hardcode a single path.
import fs from 'fs';
import path from 'path';

function exists(p) {
  try {
    return fs.existsSync(p);
  } catch {
    return false;
  }
}

export function backendCwd() {
  try {
    return process.cwd();
  } catch {
    return null;
  }
}

export function backendCandidates() {
  const out = [];
  const push = (p) => {
    if (p && !out.includes(p)) out.push(p);
  };
  push(process.env.BACKEND_DIR);
  const cwd = backendCwd();
  if (cwd) {
    push(path.join(cwd, 'backend'));
    push(path.resolve(cwd, '..', 'backend'));
  }
  push('/app/backend');
  push('/usr/src/app/backend');
  push('/srv/app/backend');
  push('/workspace/backend');
  push('/home/app/backend');
  return out.map((dir) => ({ dir, server_py: exists(path.join(dir, 'server.py')) }));
}

export function resolveBackendDir() {
  const hit = backendCandidates().find((c) => c.server_py);
  return hit ? hit.dir : null;
}
