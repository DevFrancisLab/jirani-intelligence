# Jirani Intelligence

Jirani Intelligence is an urban-planning investigation desk for the Open Agent Hackathon 2026, Track 01, “Solving Fragmented Intelligence.”

A planner submits one question. Scout Intent decides which tools are in scope, Zetaris reads registered sources, H-MEM recalls prior notes, and Meterless Nightshift may reason only over retrieved records. The result is a structured brief with findings, evidence references, uncertainty, gaps, and next steps.

## Stack

| Layer | Technology | Location |
| --- | --- | --- |
| Frontend | React + TypeScript (Vite) | `frontend/` |
| Backend | Django 4.2 + DRF | `backend/` |
| Prototype UI | Streamlit (legacy only) | `backend/legacy/` |

There was no pre-existing React or Django app in this repository. The Streamlit dashboard was the prototype. Integrations and orchestration were moved under `backend/` and exposed as JSON APIs for the React client.

## Architecture

```text
React UI  --HTTP /api/*-->  Django
                              ├─ Zetaris UI-proxy SQL
                              ├─ H-MEM memory
                              ├─ Meterless Nightshift (HTTP when enabled)
                              └─ Meterless Web cockpit handoff (when disabled)
```

Details: [docs/architecture.md](docs/architecture.md).

Zetaris is the data access and query layer that retrieves records from registered data sources for the agent.

```text
POST {ZETARIS_BASE_URL}/api/proxy/sql-editor/sqls/run-query
Authorization: Bearer <ZETARIS_API_KEY>
X-Org-ID: <numeric org id>
{"sql": "...", "limit": n}
```

Meterless Nightshift (when `METERLESS_ENABLED=true`):

```text
POST {METERLESS_BASE_URL}/chat/completions
Authorization: Bearer <METERLESS_API_KEY>
{"model": "<exact METERLESS_MODEL>", "messages": [...]}
```

Put the exact GPT-OSS 20B (NVIDIA cloud) model id into `METERLESS_MODEL`. Do not substitute Llama or another provider. A NVIDIA label is not proof of NVIDIA routing. Direct chat/completions is not full Nightshift tool-capable job orchestration. Meterless Web has no app endpoint; leave HTTP disabled and use the cockpit handoff when you only have Web.

## Install and run

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py check
python manage.py migrate
python manage.py runserver 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Requires Node.js 18+ and npm. Open http://127.0.0.1:5173. Vite proxies `/api` to Django.

More: [docs/development.md](docs/development.md).

## Environment

Canonical secrets live in the **repository-root** `.env` (gitignored). Copy placeholders:

```bash
cp .env.example .env
# or cp backend/.env.example backend/.env for backend-only overrides
```

Frontend may set only:

```bash
# frontend/.env.example
VITE_API_BASE_URL=
```

Never put Zetaris or Meterless keys in `VITE_*` variables.

Key backend variables: `ZETARIS_BASE_URL`, `ZETARIS_ORG_ID`, `ZETARIS_API_KEY`, `ZETARIS_SOURCES`, `METERLESS_ENABLED`, `METERLESS_BASE_URL`, `METERLESS_API_KEY`, `METERLESS_MODEL`, `SCOUT_SIGNING_KEY`.

## API routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health/` | Liveness |
| GET | `/api/status/` | Public config flags (no secrets) |
| POST | `/api/connections/` | Layer probes |
| POST | `/api/zetaris/probe/` | `SELECT 1` |
| POST | `/api/zetaris/sample/taxi-trips/` | NY taxi sample (not planning evidence) |
| POST | `/api/investigations/` | Run investigation `{ "question": "..." }` |
| GET | `/api/memory/` | Recent H-MEM entries |
| POST | `/api/nightshift/cockpit-answer/` | Record pasted Web cockpit answer |

## Tests

```bash
cd backend && source .venv/bin/activate
pytest -m "not live"
pytest -m live

cd frontend
npm test
npm run build
```

Mock tests do not prove live Zetaris or Nightshift. Live markers call external services.

## Integration status

| Piece | Status |
| --- | --- |
| Zetaris UI-proxy | Adapter preserved; live checks depend on the cluster |
| Meterless HTTP | Scaffolded; requires enabled flag, credentials, and a connected hotspot backend |
| Meterless Web handoff | Available when HTTP is disabled |
| H-MEM / Scout Intent | Local subsets; upstream conformance/eval not run |
| Nairobi/Kilimani planning sources | Not registered; NY taxi is sample-only |
| NVIDIA GPT-OSS 20B | Intended model label; live NVIDIA routing not verified |

## Sponsor notes

Official rule 5.1 requires Zetaris and Meterless. Rule 5.2 asks for NVIDIA where it contributes. This desk targets GPT-OSS 20B (NVIDIA cloud) through Meterless configuration without inventing an endpoint or claiming unverified execution.
