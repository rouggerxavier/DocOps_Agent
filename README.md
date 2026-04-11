# DocOps Agent

DocOps Agent is a RAG assistant for document workflows: ingest, chat, summaries, artifacts, study plans, tasks, notes, flashcards, and calendar support.

## What Is In This Repo
- Backend: FastAPI + SQLAlchemy + LangGraph + Chroma + BM25
- Frontend: React + TypeScript + Vite
- API prefix: `/api`
- Interactive API docs: `/api/docs-ui`
- Health endpoints: `/api/health` and `/api/ready`

## Quickstart (Local)

## Prerequisites
- Python `3.11+`
- Node `20+`
- A Gemini API key

## 1. Clone and install backend
```bash
git clone https://github.com/rouggerxavier/DocOps_Agent.git
cd DocOps_Agent

python -m venv .venv
```

Windows (PowerShell):
```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS:
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure environment
```bash
cp .env.example .env
```

Required in `.env`:
- `GEMINI_API_KEY`
- `JWT_SECRET_KEY`

## 3. Run backend
```bash
python -m uvicorn docops.api.app:app --host 127.0.0.1 --port 8000 --reload
```

Checks:
```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/ready
```

## 4. Run frontend
```bash
cd web
npm ci
cp .env.example .env.local
npm run dev
```

Frontend URL: `http://localhost:5173`

## Alternative (Windows helper scripts)
```powershell
.\start.ps1
.\stop.ps1
```

## Database and Migrations

Startup calls `init_db()`, which:
1. tries Alembic upgrade (`alembic upgrade head` via `run_db_migrations()`), then
2. falls back to `Base.metadata.create_all()` when migrations are disabled or unavailable.

Manual migration:
```bash
alembic upgrade head
```

Disable migration bootstrap (optional):
```env
DB_MIGRATIONS_ENABLED=false
```

## API Route Map (Current)

Public:
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/health`
- `GET /api/ready`

Authenticated highlights:
- Docs: `GET /api/docs`, `DELETE /api/docs/{doc_id}`, `GET /api/docs/{doc_id}/file`
- Ingest: `POST /api/ingest`, `/api/ingest/upload`, `/api/ingest/clip`, `/api/ingest/photo`
- Chat: `POST /api/chat`
- Summary: `POST /api/summarize`, `POST /api/summarize/async`
- Compare: `POST /api/compare`
- Artifacts:
  - `GET /api/artifacts`
  - `GET /api/artifacts/id/{artifact_id}`
  - `DELETE /api/artifacts/id/{artifact_id}`
  - legacy filename routes remain for compatibility (`/api/artifacts/{filename}`)
- Pipeline: `/api/pipeline/*`
- Study plan: `POST /api/studyplan`
- Flashcards: `GET /api/flashcards`, `POST /api/flashcards/generate`, `POST /api/flashcards/generate-batch`, review endpoints

For the full contract, open `/api/docs-ui`.

## Testing and Quality Gates

Backend:
```bash
python -m pytest -q
```

Frontend:
```bash
cd web
npm run lint
npm run build
```

CI (`.github/workflows/ci-quality-gates.yml`) runs:
- backend `pytest` on Python `3.11`
- frontend lint + build on Node `20`

## Deploy Notes

## Oracle deploy workflow
File: `.github/workflows/deploy-oracle.yml`

Current behavior:
- Runs CI gates first (backend pytest + frontend lint/build)
- Deploys to Oracle VM over SSH
- Installs backend deps with `requirements.txt` on server
  - reason: server currently runs Python `3.10`, while lockfile may include `3.11+` constrained packages
- Restarts `docops` systemd service
- Waits for `GET /api/health`

## Vercel frontend
- Root `vercel.json` builds from `web/`
- Set `VITE_API_URL` in Vercel project environment to backend public URL

## Runbooks

Operational runbooks:
- [Oracle deploy runbook](docs/runbooks/oracle-deploy.md)
- [Manual smoke runbook](docs/runbooks/manual-smoke.md)

## Repository Layout (High level)
- `docops/`: backend application
- `web/`: frontend application
- `tests/`: backend tests
- `.github/workflows/`: CI/CD workflows
- `docker/`, `docker-compose.yml`: container setup
- `alembic/`: DB migration scripts

## Notes
- Prefer changing configuration in `docops/config.py` + `.env.example`, not scattered `os.getenv()` usage.
- Keep docs and runbooks aligned with actual workflows after each phase/PR.
