# Document Copilot

An internal AI chatbot that lets analysts query a corpus of documents in plain English and get sourced, citable answers.

## The client

**Driftwood Capital** — fictional independent investment research firm. Their analysts spend half their week reading 10-Ks and 10-Qs before they can produce any original analysis. Document Copilot eats that intake work so they can skip straight to insight.

Full brief: [docs/client-brief.md](docs/client-brief.md)

## Stack

| Layer              | Choice                                               |
| ------------------ | ---------------------------------------------------- |
| Backend            | Python + FastAPI                                     |
| Frontend           | Vite + React SPA + TypeScript                        |
| Database           | Supabase Postgres (users, chats, documents, chunks)  |
| Migrations         | SQLAlchemy models + Alembic                          |
| Retrieval          | Supabase `pgvector` + Postgres full-text search      |
| Auth               | Supabase Auth (email only)                           |
| Hosting            | Railway                                              |
| LLM + embeddings   | OpenAI                                               |

## Repo layout

```text
document-copilot/
├── AGENTS.md           # agent instructions (read first)
├── README.md           # this file
├── data/               # local corpus + download script (payloads gitignored)
├── docs/
│   └── client-brief.md # the client one-pager
├── backend/            # FastAPI service
└── frontend/           # React SPA (Vite)
```

## Prerequisites

Install these before setting up `backend/` or `frontend/`:

| Tool | Version | Used for | Install |
| ---- | ------- | -------- | ------- |
| [Python](https://www.python.org/downloads/) | 3.12+ | Backend runtime | OS package manager or python.org |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | latest | Backend deps + `data/download.py` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Node.js](https://nodejs.org/) | 20+ (LTS) | Frontend toolchain | nodejs.org or `nvm install --lts` |
| [pnpm](https://pnpm.io/installation) | latest | Frontend package manager | `corepack enable && corepack prepare pnpm@latest --activate` |

You also need accounts/keys for external services once the app is wired up. Start with [docs/guides/supabase-setup.md](docs/guides/supabase-setup.md) (account + project), then create an [OpenAI API key](https://platform.openai.com/api-keys) when the LLM layer is wired up.

## Running locally

Setup guides (credentials, schema, why this stack):

- [Supabase](docs/guides/supabase-setup.md) — account, hosted project (dashboard or CLI)
- [Backend](docs/guides/backend-setup.md)
- [Frontend](docs/guides/frontend-setup.md)

Copy env templates (do not commit filled files):

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Fill `backend/.env` and `frontend/.env` from the Supabase dashboard and an OpenAI key. Use the **direct** Postgres URL for `DATABASE_URL` (not the transaction pooler).

```bash
# schema
cd backend
uv sync
uv run alembic upgrade head

# corpus (from repo root): download HTML, convert to Markdown, ingest
cd ..
uv run data/download.py
uv run data/convert_to_markdown.py
cd backend
uv run python -m ingest.load_source_documents
uv run python -m ingest.chunk_and_embed --all

# API
uv run uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
pnpm install
pnpm dev
```

Sign in at http://localhost:5173 (email auth). Fast tests: `cd backend && uv run pytest -m "not integration"`. Live agent smoke (OpenAI + Postgres, does not persist chats): `cd backend && uv run python -m scripts.smoke_agent`.

## Deploy

Railway runs two services from this GitHub repo (`main`). Do not deploy from the repo root.

| Service | Root directory | Notes |
| --- | --- | --- |
| backend | `/backend` | [backend/railway.json](backend/railway.json) sets `uvicorn app.main:app` and `/health`. Point Config as Code at `/backend/railway.json` (Railway does not search inside the root directory for that file). |
| frontend | `/frontend` | Vite SPA via Caddy. Do **not** set a custom start command. |

`VITE_*` vars are baked in at **build** time. Set `VITE_API_BASE_URL` to the backend origin (no trailing slash) plus `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` before the frontend build. After the frontend has a public URL, set backend `ALLOWED_ORIGINS` to that origin (and `http://localhost:5173` if you still develop locally). In Supabase Auth, add the frontend origin as Site URL and a Redirect URL; keep localhost for local sign-in.

Production (Railway):

- Backend: https://backend-production-c764.up.railway.app
- Frontend: https://frontend-production-57d1.up.railway.app

## CI and git hooks

GitHub Actions (`.github/workflows/ci.yml`) runs on pull requests and pushes to `main`: backend `ruff` + `pytest -m "not integration"`, frontend `tsc` + `eslint`.

Install pre-commit after a backend `uv sync` (the hook CLI is a backend dev dependency):

```bash
cd backend
uv sync
uv run pre-commit install
```

Hooks run on `git commit` (ruff, fast pytest, frontend tsc/lint). Same checks as CI.

## Sample SEC data

Use the standalone downloader to fetch a small local 10-K sample from SEC EDGAR.
Edit the params at the top of `data/download.py`, especially `USER_AGENT`, then run:

```bash
uv run data/download.py
```

By default this downloads the latest 5 10-K filings for AAPL, MSFT, NVDA, AMZN, and GOOGL into year folders under `data/downloads/` and writes a `manifest.json`.
Downloaded files are gitignored; the `data/` folder itself stays in git for the script and notes.
