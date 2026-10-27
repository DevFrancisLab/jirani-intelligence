# Architecture

```text
Browser (React + TypeScript)
        |
        |  HTTP JSON  /api/*
        v
Django backend (DRF)
        |
        +--> agent/orchestrator.py   Scout Intent contract
        +--> integrations/zetaris.py UI-proxy SQL
        +--> integrations/hmem.py    investigation memory
        +--> integrations/meterless_nightshift.py  chat/completions when enabled
        +--> integrations/nightshift_web.py        cockpit handoff when disabled
```

## Boundaries

- **Frontend** never holds Zetaris or Meterless credentials. Only `VITE_API_BASE_URL` is public.
- **Backend** loads the repository-root `.env` (canonical) and optional `backend/.env`.
- **Zetaris** uses the verified UI-proxy route `POST {ZETARIS_BASE_URL}/api/proxy/sql-editor/sqls/run-query`.
- **Meterless** HTTP path uses the exact `METERLESS_MODEL` from configuration. No silent Llama/OpenAI fallback. A NVIDIA label is not proof of NVIDIA routing.
- **H-MEM** persists under `backend/data/` (gitignored) and preserves standing labels for evidence vs AI interpretation.
- **Streamlit** under `backend/legacy/` is a prototype only. The primary UI is React.

## Verified vs not verified

| Piece | Status |
| --- | --- |
| Zetaris UI-proxy adapter | Previously live-verified for `SELECT 1` and NY taxi sample; re-check after moves |
| Meterless HTTP inference | Scaffolded; live only when hotspot backend is connected |
| Meterless Web cockpit | Manual handoff path when HTTP is disabled |
| H-MEM / Scout Intent | Local unit-tested subsets; upstream suites not run |
| Planning sources for Nairobi/Kilimani | Not registered |
