import fs from 'fs';
import net from 'net';
import { spawn } from 'child_process';

// Starts the FastAPI backend from inside the Next.js server process.
//
// Why this exists: this app was scaffolded from a Next.js-only template, so the
// production image builds and runs Next.js on :3000 but never starts
// `uvicorn server:app` on :8001. Every /api/* call is proxied to :8001 and gets
// ECONNREFUSED. In preview, supervisord starts the backend, so this must stay out of
// the way there.
//
// Guards: it never runs if something is already listening on :8001, it never runs if
// no python/uvicorn binary exists in the image, and by default it only runs when
// NODE_ENV=production. Set BACKEND_AUTOSTART=1 to force it on, 0 to force it off.

const HOST = '127.0.0.1';
const PORT = Number(process.env.FASTAPI_PORT || 8001);
const BACKEND_DIR = process.env.BACKEND_DIR || '/app/backend';
const MAX_ATTEMPTS = Number(process.env.BACKEND_AUTOSTART_MAX_RETRIES || 5);

const UVICORN_CANDIDATES = [
  '/root/.venv/bin/uvicorn',
  '/usr/local/bin/uvicorn',
  '/usr/bin/uvicorn',
];
const PYTHON_CANDIDATES = [
  '/root/.venv/bin/python',
  '/usr/local/bin/python3',
  '/usr/bin/python3',
];

let initialised = false;
let attempts = 0;

function log(...args) {
  console.log('[backend-autostart]', ...args);
}

function firstExisting(paths) {
  for (const p of paths) {
    try {
      if (fs.existsSync(p)) return p;
    } catch {
      /* ignore */
    }
  }
  return null;
}

function portOpen(timeoutMs = 1000) {
  return new Promise((resolve) => {
    const socket = net.connect({ host: HOST, port: PORT });
    const finish = (open) => {
      try {
        socket.destroy();
      } catch {
        /* ignore */
      }
      resolve(open);
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => finish(true));
    socket.once('timeout', () => finish(false));
    socket.once('error', () => finish(false));
  });
}

function resolveCommand() {
  const args = ['server:app', '--host', '0.0.0.0', '--port', String(PORT), '--workers', '1'];
  const uvicorn = firstExisting(UVICORN_CANDIDATES);
  if (uvicorn) return { cmd: uvicorn, args };
  const python = firstExisting(PYTHON_CANDIDATES);
  if (python) return { cmd: python, args: ['-m', 'uvicorn', ...args] };
  return null;
}

function isEnabled() {
  const flag = String(process.env.BACKEND_AUTOSTART || '').toLowerCase();
  if (['0', 'false', 'off', 'no'].includes(flag)) return false;
  if (['1', 'true', 'on', 'yes'].includes(flag)) return true;
  return process.env.NODE_ENV === 'production';
}

function launch(resolved) {
  attempts += 1;
  log('starting FastAPI (attempt ' + attempts + '/' + MAX_ATTEMPTS + '):', resolved.cmd, resolved.args.join(' '));

  const child = spawn(resolved.cmd, resolved.args, {
    cwd: BACKEND_DIR,
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  child.stdout.on('data', (d) => process.stdout.write('[fastapi] ' + d));
  child.stderr.on('data', (d) => process.stderr.write('[fastapi] ' + d));

  child.on('error', (e) => log('spawn failed:', String(e)));

  child.on('exit', (code, signal) => {
    log('FastAPI exited (code=' + code + ' signal=' + signal + ')');
    if (attempts >= MAX_ATTEMPTS) {
      log('giving up after ' + attempts + ' attempts - check the [fastapi] lines above for the traceback');
      return;
    }
    const delay = Math.min(30000, 2000 * Math.pow(2, attempts - 1));
    log('retrying in ' + delay + 'ms');
    setTimeout(() => launch(resolved), delay);
  });

  const stop = () => {
    try {
      child.kill('SIGTERM');
    } catch {
      /* ignore */
    }
  };
  process.once('SIGTERM', stop);
  process.once('SIGINT', stop);
}

export async function ensureBackend() {
  if (initialised) return;
  initialised = true;

  if (!isEnabled()) {
    log('disabled (NODE_ENV=' + process.env.NODE_ENV + ', BACKEND_AUTOSTART=' + (process.env.BACKEND_AUTOSTART || 'unset') + ') - not starting anything');
    return;
  }

  if (!fs.existsSync(BACKEND_DIR + '/server.py')) {
    log('no backend source at ' + BACKEND_DIR + '/server.py - nothing to start');
    return;
  }

  if (await portOpen()) {
    log('something is already listening on ' + HOST + ':' + PORT + ' - leaving it alone');
    return;
  }

  const resolved = resolveCommand();
  if (!resolved) {
    log(
      'ERROR: nothing is listening on :' + PORT + ' and no python/uvicorn runtime exists in this image. ' +
        'The FastAPI backend cannot be started here. This is a build/template problem - the deployment ' +
        'needs to run both Next.js and the Python backend.',
    );
    return;
  }

  launch(resolved);
}
