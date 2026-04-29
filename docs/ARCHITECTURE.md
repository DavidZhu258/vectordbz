# Architecture

VectorDBZ v2.0 is an evidence-first information aggregation harness. It is built
to collect a few thousand records per day, keep only the useful structure, and
serve cited daily intelligence through a small API that the existing v1 UI can
reuse.

## Design Goals

- Keep the system small enough to maintain on independent Hong Kong and US
  servers.
- Separate source collection from ranking, narration, and question answering.
- Store evidence before generating prose.
- Treat provider limits and source failures as normal operational states.
- Keep secrets in environment files or server secret stores, never in git.

## Runtime Flow

```text
source registry
  -> collectors
  -> ClickHouse analytics_v2.articles
  -> embedding worker
  -> Qdrant articles_v2
  -> rerank worker
  -> report contract
  -> LLM narrative
  -> FastAPI /api/v2
```

The LLM is deliberately late in the flow. It receives a compact, deterministic
contract rather than raw feeds.

## Storage

ClickHouse database: `analytics_v2`

| Table | Purpose |
| --- | --- |
| `articles` | Source-aware canonical records. |
| `pipeline_state` | Health, checkpoints, table inventory, and watchdog state. |
| `rerank_cache` | Idempotent rerank results by date, theme, source, and record. |
| `trend_reports` | Deterministic report contract plus LLM narrative JSON. |

Qdrant collection: `articles_v2`

- 512-dimensional embeddings.
- Payload indexes for `source_type`, `sub_source`, and `collected_at`.
- Used for retrieval and Q&A evidence lookup.

## Source Taxonomy

The core source types are:

- `github_repo`
- `hf_model`
- `hf_dataset`
- `hf_space`
- `reddit_subtrend`
- `paper_candidate`
- `job_market`
- `news`

This avoids the v1.0 failure where everything could become a generic news item.
Reports can cap and compare each source family instead of letting one noisy
source dominate the day.

## Core Modules

| Module | Responsibility |
| --- | --- |
| `config.py` | Environment-only runtime configuration. |
| `db.py` | ClickHouse and Qdrant schema, reads, and writes. |
| `source_registry.py` | Source definitions, criticality, and quality rules. |
| `collectors.py` | Live and V1-backed source collectors. |
| `source_backfill.py` | Historical day-by-day backfill into v2 rows. |
| `embed_worker.py` | Batched embeddings with bounded failure handling. |
| `rerank_worker.py` | Theme/source reranking and cache writes. |
| `report_contract.py` | Deterministic compact report payload. |
| `trend_analyzer.py` | LLM narration over the deterministic contract. |
| `evidence_contract.py` | Cited Q&A payloads and answerability rules. |
| `long_task_runner.py` | Resumable phase orchestration. |
| `api.py` | FastAPI v2 health and ask endpoints. |

## Failure Handling

Source failures are isolated by source. Optional sources degrade a run. Critical
sources block publication only when freshness or evidence coverage is not good
enough. Long tasks write checkpoints so collection, embedding, rerank, and report
generation can resume after provider throttling, server restarts, or process
crashes.

## Deployment Shape

Each server runs the same directory layout:

```text
/opt/vectordbz-v2-harness
/opt/vectordbz-v2-harness/.venv
/etc/vectordbz/v2.env
/var/lib/vectordbz_v2/checkpoints
```

The repository ships only templates. Real provider tokens, database passwords,
SSH credentials, and server-specific addresses are written to server-local
environment files.

## UI Strategy

The v1 UI is reused as the operational surface. v2 adds only the screens needed
for a compact intelligence workflow:

- Source Health
- Daily Signals
- Evidence Drawer
- Ask With Citations
- Backfill and Runner Status
