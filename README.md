# Jirani Intelligence

Jirani Intelligence is an urban-planning investigation desk for the Open Agent Hackathon 2026, Track 01, “Solving Fragmented Intelligence.”

A planner submits one question. The desk does not answer from memory. Scout Intent decides which tools are in scope, Zetaris reads registered sources, and Meterless Nightshift may reason only over the rows that came back. The result is a brief with findings, supporting records, uncertainty, evidence gaps, and next steps.

Zetaris and Nightshift are not marked working in this repository. Unit tests cover the workflow with fake responses. A live call is the only thing that can change that.

## Architecture

```text
Question
  -> Scout Intent          signs an execution contract
  -> Zetaris               retrieves records from registered sources
  -> Meterless Nightshift  reasons over those records
  -> Structured brief
```

Zetaris is the data access and query layer that retrieves records from registered data sources for the agent. It sits between the signed contract and the reasoning step. The agent never invents a table name. It may run `SHOW LIGHTNING DATABASES` and `SHOW DATASOURCES`, and `SELECT * FROM <registered source> LIMIT n` for names listed in `ZETARIS_SOURCES`.

Meterless Nightshift is the AI provider. It is the local OpenAI-compatible API, by default `http://127.0.0.1:8088/v1`. The reasoning request uses `meterless/auto` unless `METERLESS_MODEL` says otherwise. Findings that do not cite a retrieved record id are discarded.

The Meterless engine in this workflow is **Scout Intent**. It is the engine that runs before any action: it classifies intent, guards the prompt, routes to tools, and signs an execution contract. The implementation in `integrations/meterless_engine.py` is the Stage-1 deterministic pipeline for two planning intents. Stage-2 semantic scoring is not included, and the upstream Scout eval harness has not been run. Spec: [engines/scout-intent/AGENTS.md](https://github.com/Meterless/Meterless/blob/main/engines/scout-intent/AGENTS.md).

```text
app.py                              Streamlit dashboard
agent/orchestrator.py               contract -> query -> reason -> brief
agent/config.py                     environment, no secrets in repr
integrations/zetaris.py             Zetaris UI-proxy query client
integrations/meterless_nightshift.py
integrations/meterless_engine.py    Scout Intent
```

## Sponsor technology

| Piece | Role in this desk | Status |
| --- | --- | --- |
| Zetaris | Data access and query layer for registered sources | Adapter written. Live query not verified. |
| Meterless Nightshift | AI provider for the reasoning step | Adapter written. Live completion not verified. |
| Scout Intent | Meterless engine that signs the execution contract | Local Stage-1 pipeline covered by unit tests. Upstream eval harness not run. |
| NVIDIA | Not integrated | No verified Nemotron or GPU workload on the 8 GB Mac path. |
| Cursor | Used to write this repository | Development tool, not a runtime dependency. |

Official rule 5.1 requires Zetaris and Meterless. Rule 5.2 asks for NVIDIA where it contributes. Adding a NVIDIA call that does not run would not be a contribution, so it is absent.

Supplied Zetaris samples such as `NY_TAXI`, `TPCDS`, and `TPCH` are excluded from planning evidence. Registering one of those names in `ZETARIS_SOURCES` is ignored.

## Installation

The machine this project was set up on has Python 3.9.6. Streamlit 1.50 and newer require Python 3.10, so `requirements.txt` stays on the last 3.9-compatible Streamlit line.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.venv/` is gitignored. Do not commit it.

## Setup

```bash
cp .env.example .env
```

Edit `.env`. Leave unknown credentials empty. The file is gitignored.

Zetaris:

- `ZETARIS_BASE_URL` is the UI origin, such as `http://localhost:3000`, with no path.
- `ZETARIS_ORG_ID` is the numeric organisation id.
- Set `ZETARIS_API_KEY`, or both `ZETARIS_USERNAME` and `ZETARIS_PASSWORD`.
- `ZETARIS_SOURCES` lists sources the desk may query: `qualified_name|what one row represents`, separated by `;;`.

Nightshift:

- Run Nightshift locally.
- `METERLESS_BASE_URL` defaults to `http://127.0.0.1:8088/v1`.
- Copy the runtime token from Nightshift’s `proxy-token` file into `METERLESS_RUNTIME_TOKEN`.

Scout Intent:

- `SCOUT_SIGNING_KEY` is a local integrity key for contract signatures. It is not a sponsor credential. If it is empty, the process uses an ephemeral key and earlier contracts will not verify after a restart.

The dashboard loads this file on the server with `python-dotenv`. Secrets are not written into the page, test assertions, or logs.

## Usage

```bash
source .venv/bin/activate
streamlit run app.py
```

Open the URL Streamlit prints. Enter a question such as “Which registered records mention housing permits?” or “What data sources are registered?”

**Run investigation** builds the brief. **Check connections** calls Zetaris with `SELECT 1` and Nightshift with `GET /v1/models`. `SELECT 1` only proves the query path answered. It is not planning evidence. A failed check stays failed.

An empty catalog is a real result. A blocked prompt, a low-confidence intent, or a missing credential produces a brief with no findings and no invented rows.

## Testing

```bash
source .venv/bin/activate
pytest
```

The tests cover configuration redaction, the Zetaris and Nightshift adapters, Scout Intent contracts, and the investigation workflow. HTTP is replaced with an in-memory transport. They prove that missing services, refused contracts, uncited model text, and sample databases do not become planning evidence. They do not prove that Zetaris or Nightshift is running.

## Limitations

- Live Zetaris and Nightshift integrations are unverified until this machine has the services and credentials.
- Scout Intent here is a small Stage-1 registry, not a conformance result against the Meterless eval harness. Semantic rescoring and the rate-limit guard are not implemented.
- Nightshift wording is kept only when it cites record ids. Those sentences are not checked against the cell values.
- The desk does not create Zetaris sources, infer join keys, or crawl unregistered databases.
- Query results are capped at 100 rows, and the default is 25, so an 8 GB machine is not asked to pull a full table.
- Execution contracts expire after five minutes.
- There is no NVIDIA path.

## Official submission rules

Checked on 26 October 2026 at the [event page](https://hackathon.genai.works/event/open-agent-hackathon-2026). Section 06 requires a 1–4 minute demo video (6.1), a slide deck (6.2), this repository and README (6.3), and an explanation of Zetaris, Meterless, Cursor, and NVIDIA (6.4). The rules do not publish a `metadata.json` schema. `metadata.json` records the same sponsor explanation for the track.
