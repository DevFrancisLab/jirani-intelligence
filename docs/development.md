# Development

## Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py check
python manage.py migrate
python manage.py runserver 8000
```

Credentials: keep them in the repository-root `.env`. Copy placeholders from root or `backend/.env.example`. Never commit `.env`.

Tests:

```bash
cd backend
source .venv/bin/activate
pytest -m "not live"
pytest -m live   # external services only; may fail if offline or disabled
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL (default http://127.0.0.1:5173). The dev server proxies `/api` to Django on port 8000. Optionally set `VITE_API_BASE_URL` in `frontend/.env` to an absolute API origin; never put provider secrets there.

```bash
npm test
npm run build
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Frontend “Backend unavailable” | Django not running, or CORS origin mismatch |
| Zetaris `not_configured` | Root `.env` missing UI origin, org id, or API key |
| Nightshift `hotspot_offline` | Session Hotspot tab closed / companion not running |
| Nightshift `disabled` | `METERLESS_ENABLED=false` |
| Empty findings with no planning rows | Register real sources in `ZETARIS_SOURCES`; NY taxi is sample-only |

## Legacy Streamlit

```bash
cd backend
source .venv/bin/activate
streamlit run legacy/streamlit_app.py
```

Prefer the React UI for demos.
