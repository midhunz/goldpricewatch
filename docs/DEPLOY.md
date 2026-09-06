# Deploying with GitHub Actions

**Workflow:** `.github/workflows/deploy.yml` · **Triggers:** push to `main`, or manual dispatch

---

## Read this before you enable it

The frontend source in this repo produces **6** of the **34** routes production serves.
A plain `docker build ./frontend` followed by a deploy would return **404 for 28 live
pages** — every country page, city page and emirate page, plus `/about` and `/contact`.

So the pipeline deliberately does **not** deploy the frontend image. It is gated behind
`scripts/check_frontend_routes.py`, which fails while any production route is missing from
`frontend/src`. The gate stays shut until the source is restored (`docs/BLOCKED.md`).

## What each push to `main` actually ships

| Thing | Ships? | How |
|---|---|---|
| Backend image | Yes | Built from `./backend`, pushed to Docker Hub, pinned to the commit SHA |
| `/gold-rates/*.html` | Yes | `git pull` on the server — Caddy serves them from the checkout |
| `Caddyfile`, `docker-compose.prod.yml` | Yes | Same `git pull` |
| **Frontend image** | **No** | Blocked by the route guard |

### Why the static pages don't need an image build

`Caddyfile` serves `/gold-rates/*` from `/srv/static`, which
`docker-compose.prod.yml` bind-mounts read-only from `./frontend/public`. Caddy `handle`
blocks match in order, so this wins over the catch-all proxy to the frontend, and the stale
copies still baked into the frontend image are never reached.

This is what lets the T1.1 hotfix ship today without touching the frontend.

---

## One-time setup

### 1. Repository secrets

`Settings > Secrets and variables > Actions > Secrets`

| Secret | Value |
|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub username (`midhunpottammal`) |
| `DOCKERHUB_TOKEN` | Docker Hub access token — **not** the account password |
| `DROPLET_HOST` | Droplet IP or hostname |
| `DROPLET_USER` | SSH user (`root`, or a deploy user) |
| `DROPLET_SSH_KEY` | Private key, full PEM including the BEGIN/END lines |

### 2. Repository variables

`Settings > Secrets and variables > Actions > Variables`

| Variable | Value |
|---|---|
| `HEALTHCHECK_URL` | `https://goldpricewatch.com/api/health` |
| `NEXT_PUBLIC_API_URL` | `https://goldpricewatch.com/api` — only used by frontend builds |

### 3. Environment

Create an Environment named **`production`** (`Settings > Environments`). The `deploy` job
targets it, and the job will not run without it. Add required reviewers there if you want
deploys to pause for approval.

### 4. Server preparation

The `deploy` job assumes `~/app` on the droplet is a git checkout of this repo whose
`origin` is reachable by the deploy user:

```bash
ssh <user>@<host>
cd ~ && git clone <repo-url> app && cd app
git remote -v          # must resolve without an interactive prompt
docker compose version # must exist
```

If the repo is private, give the server a deploy key or a credential helper — the workflow
runs `git fetch` as that user and will fail on a password prompt.

---

## Deploy

**Automatic:** merge to `main`.

**Manual:** Actions → Deploy → Run workflow. Leave *"Also rebuild and deploy the frontend
image"* **unchecked** — with the source incomplete, checking it is a no-op, because the
route guard blocks the job regardless.

### What runs, in order

1. **Guardrails** — the 60 data/SEO tests (`tests/`), the frontend route guard, and a check
   that every required secret and variable is set. Nothing ships if this fails.
2. **Build & push backend** — tagged `latest` and the commit SHA.
3. **Deploy** — records the currently-deployed tag for rollback, `git reset --hard
   origin/main`, `docker compose pull backend`, `up -d`.
4. **Smoke test** — `HEALTHCHECK_URL`, 12 attempts, 10s apart.
5. **Verify static rate pages** — fetches `kerala.html` from production and fails if it is
   missing `noindex` or serving a rupee figure. This is the check that would have caught
   T1.1 in the first place.
6. **Roll back** — on any failure above, redeploys the previous tag.

---

## Deploying the frontend, once the source is restored

1. Restore the missing routes into `frontend/src/app`.
2. `python scripts/check_frontend_routes.py` — must exit 0.
3. Actions → Deploy → Run workflow → tick **deploy_frontend**.

`frontend/Dockerfile` now declares `ARG NEXT_PUBLIC_API_URL` and **fails the build** if it
is empty. Previously the arg was passed by CI but never declared, so it was silently
discarded and the client bundle fell back to the `|| "http://localhost:8000"` default in
`src/hooks/useGoldRates.ts` — pointing every client-side fetch at the visitor's own machine.
Server-rendered prices still worked, which is why this went unnoticed.

When you add a route, add it to `.github/expected-routes.txt` in the same commit. When you
legitimately remove one, delete its line.

---

## Known issues in the deployment config

Not changed here, because they alter runtime behaviour and deserve a deliberate decision.

**`docker-compose.prod.yml` publishes Postgres to the internet.**

```yaml
db:
  environment:
    - POSTGRES_USER=user
    - POSTGRES_PASSWORD=password
  ports:
    - "5432:5432"        # reachable from anywhere
```

Port 5432 is bound on all interfaces with the credentials `user` / `password`, both
committed to the repo. Anyone who scans the host's ports has the database. Fix by dropping
the `ports:` block entirely — `backend` reaches `db` over the compose network and does not
need it published — and moving the credentials to environment variables. Then rotate them.

**`backend` and `frontend` also publish 8000 and 3000 directly**, so both can be reached
over plain HTTP, bypassing Caddy and TLS. Bind them to `127.0.0.1` or remove the `ports:`
entries, since Caddy proxies to them over the compose network.

**`.env` holds the Supabase production password in plaintext** and the key is malformed
(`SUBA_BASE_URL:` uses a colon, so `os.environ.get("SUBA_BASE_URL")` never reads it).
Rotate it and move it to a secret store.
