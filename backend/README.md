# Backend (FastAPI)

Python API for Document Copilot — auth, chat, retrieval, and LLM orchestration.

## Setup

```bash
cd backend
cp .env.example .env   # fill in Supabase + OpenAI values
uv sync
```

Config lives in `app/config.py` and reads `backend/.env`. Use the **uv venv** (`.venv/bin/python`), not system Python.

In Cursor: select interpreter `backend/.venv/bin/python`.

## Run

```bash
cd backend
uv run uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Health: http://127.0.0.1:8000/health
- Docs: http://127.0.0.1:8000/docs

## Migrations (when schema exists)

```bash
cd backend
uv run alembic upgrade head
```

## Lint & test

```bash
cd backend
uv run ruff check .
uv run pytest -m "not integration"
```

Git hooks and GitHub Actions: [root README](../README.md#ci-and-git-hooks). Enable hooks with `uv run pre-commit install` from `backend/` after `uv sync`.

More detail: [docs/guides/backend-setup.md](../docs/guides/backend-setup.md)
