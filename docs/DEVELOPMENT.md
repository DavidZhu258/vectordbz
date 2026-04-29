# Development Guide

This guide is for the VectorDBZ v2.0 information aggregation harness.

## Prerequisites

- Python 3.11 or later
- ClickHouse for `analytics_v2`
- Qdrant for `articles_v2`
- Provider keys supplied through environment variables when running live
  embedding, rerank, or LLM narration

Do not put provider tokens, database passwords, SSH credentials, or PATs in this
repository.

## Local Setup

```powershell
git clone https://github.com/DavidZhu258/vectordbz.git
cd vectordbz
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r deploy\vectordbz_v2\requirements.txt pytest
```

Create local environment variables in your shell or in an ignored local file.
The checked-in examples under `profiles/` are templates only.

Common variables:

```powershell
$env:CLICKHOUSE_HOST = "127.0.0.1"
$env:CLICKHOUSE_PORT = "8123"
$env:CLICKHOUSE_DB = "analytics_v2"
$env:QDRANT_URL = "http://127.0.0.1:6333"
$env:VDBZ_API_PORT = "4640"
```

Provider variables are optional for unit tests but required for live embedding,
rerank, and narration:

```powershell
$env:JINA_API_KEY = "<set outside git>"
$env:DEEPINFRA_API_KEY = "<set outside git>"
$env:OPENROUTER_API_KEY = "<set outside git>"
```

## Verification Commands

Run unit and contract tests:

```powershell
python -m pytest tests\vectordbz_v2 -q
```

Initialize runtime schema:

```powershell
python -m vectordbz_v2.init_schema
```

Run smoke and health checks:

```powershell
python -m vectordbz_v2.test_smoke
python -m vectordbz_v2.collector_health --limit 1
```

Dry-run historical source selection:

```powershell
python -m vectordbz_v2.source_backfill --start 2026-04-01 --end 2026-04-28 --per-day-limit 20 --dry-run
```

Run a bounded resumable pipeline:

```powershell
python -m vectordbz_v2.long_task_runner `
  --collect-live `
  --github-limit 2 `
  --hf-limit-per-type 1 `
  --embed-max 40 `
  --embed-batch 4 `
  --rerank-days 30 `
  --checkpoint-path .codex/checkpoints/v2-long-task.json `
  --resume
```

## Running the API

```powershell
uvicorn vectordbz_v2.api:app --host 0.0.0.0 --port 4640
```

Useful endpoints:

- `GET /api/v2/health`
- `POST /api/v2/ask`

## Server Deployment

Use a clean tag or commit, not an unreviewed working tree.

```bash
python3 -m venv /opt/vectordbz-v2-harness/.venv
/opt/vectordbz-v2-harness/.venv/bin/python -m pip install -U pip
/opt/vectordbz-v2-harness/.venv/bin/python -m pip install -r deploy/vectordbz_v2/requirements.txt
cp profiles/us.env.example /etc/vectordbz/v2.env
vi /etc/vectordbz/v2.env
/opt/vectordbz-v2-harness/.venv/bin/python -m vectordbz_v2.init_schema
systemctl enable --now vectordbz-v2-api
```

The systemd unit is in `deploy/vectordbz_v2/vectordbz-v2-api.service`.

## Commit Hygiene

Before committing:

```powershell
git status --short
git diff --check
python -m pytest tests\vectordbz_v2 -q
```

Scan tracked files for secrets and generated artifacts. The repository should not
contain `.env`, provider tokens, database passwords, local archives, vector
stores, screenshots, node_modules, or local Codex summaries.
