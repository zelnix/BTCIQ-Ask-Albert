# Emergent Support Escalation — btciq.app

> Copy the message below into the Emergent in-app Support channel (or reply to your existing ticket).
> Preview works fully; this is a **production-only** deployment issue.

---

**Subject:** Production deploy not starting my FastAPI backend — btciq.app shows "Engine error" (all /api calls return HTML, not JSON)

## Summary
My deployed app at **https://btciq.app** loads the Next.js frontend but the **FastAPI backend is not running in the production container**. Every `/api/v1/*` request returns an HTML error page instead of JSON, so the app shows an "Engine error" screen:

> `SyntaxError: Unexpected token '<', "<!DOCTYPE "... is not valid JSON`

The **preview** environment works perfectly — this is **production-only**.

## Architecture
- Frontend: **Next.js** (port 3000)
- Backend: **FastAPI** — `uvicorn server:app` on **port 8001**, working dir `/app/backend`, venv `/root/.venv`
- DB: MongoDB (Emergent-managed)
- The Next.js catch-all proxy (`/app/app/api/[[...path]]/route.js`) forwards `/api/*` → `http://localhost:8001`. If the backend isn't running, `/api/*` fails.

## Root cause (as far as I can tell)
- In **preview**, the backend is started by a supervisor program (`[program:backend]` / uvicorn on 8001).
- In **production**, the backend does **not** start. The supervisor config `/etc/supervisor/conf.d/supervisord.conf` is labelled "READONLY — DO NOT EDIT" and the deploy build appears to regenerate it, so any backend program entry I add in preview does **not** persist into the production image.
- This project was originally scaffolded as a **Next.js-only** template; the FastAPI backend was added later, which is likely why the production deploy doesn't know to run it.

## What I need
Please enable/register the FastAPI backend service so it starts in the **production** deployment, using:

```ini
[program:backend]
command=uvicorn server:app --host 0.0.0.0 --port 8001 --workers 1
environment=PATH="/root/.venv/bin:/usr/local/bin:/usr/bin:/bin"
directory=/app/backend
autostart=true
autorestart=true
```
> Note: command uses `uvicorn` on PATH (NOT the absolute `/root/.venv/bin/uvicorn`, which doesn't exist in the production container).

### ⚠️ Key point — this is a BUILD-LEVEL change, not a republish
My app was scaffolded from a **Next.js-only** template, so a normal republish keeps rebuilding a **frontend-only image** and never brings the backend up. This needs a **build-level change**: please **convert/migrate my deployment build to a fullstack template** that runs **both** services in the production container — Next.js on :3000 **and** the FastAPI backend on :8001. My codebase already passes the deployment readiness check, so once the build runs both services it should work immediately.

## Production environment variables that must be set
(Backend reads these; if missing the backend degrades or fails.)
- `EMERGENT_LLM_KEY`
- `ADMIN_PASSCODE`
- `FRED_API_KEY`
- `GLASSNODE_API_KEY`
- `MONGO_URL`, `DB_NAME` (I believe these are auto-injected by the platform — please confirm)

## What I've already verified
- Preview: backend healthy — `GET /api/v1/health` → 200; `GET /api/v1/dashboard` → `status:"ready"`.
- Deployment readiness check passes in preview.
- Confirmed the failing production requests return HTML (not the proxy's JSON 502), which indicates the backend service isn't present/started in the production container.

## Questions
1. What's the supported way to run a **secondary FastAPI backend** (port 8001) alongside Next.js in an Emergent deployment for this project?
2. Do I need my backend defined anywhere specific (e.g., a particular file the build reads) for it to be included in the production image?
3. Are the MongoDB env vars auto-injected in production, or do I need to set them?

**App:** btciq.app · **Project:** (your Emergent project name/ID)

---

# Appendix — Preview environment evidence
(Proving the backend works; only production fails to start it.)

**1) Supervisor status (preview) — backend runs fine here:**
```
backend    RUNNING   pid 47, uptime 0:44:09
mongodb    RUNNING   pid 48, uptime 0:44:09
nextjs     RUNNING   pid 49, uptime 0:44:09
```

**2) Backend startup log (preview) — /var/log/supervisor/backend.out.log:**
```
INFO:     Started server process [105]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

**3) Direct backend health — GET http://localhost:8001/api/v1/health → 200:**
```json
{"status":"ok","compute_status":"idle","error":null,"runs":37}
```

**4) Direct backend data — GET /api/v1/dashboard → 200 (real Kraken data):**
```json
{"status":"ready","signal":"UP","quant_score":60,"data_source":"kraken"}
```

**5) Through the Next.js proxy — GET http://localhost:3000/api/v1/health → HTTP 200:**
```json
{"status":"ok","compute_status":"idle","error":null,"runs":37}
```

**Conclusion:** In preview the FastAPI backend starts, serves JSON directly (`:8001`) and through the Next.js proxy (`:3000/api/*`). On **production (btciq.app)** the identical `/api/*` requests return an HTML page instead of JSON — i.e., the backend service is not being started in the production container. Please enable `[program:backend]` (uvicorn `server:app` on port 8001, dir `/app/backend`) in the production deployment.
