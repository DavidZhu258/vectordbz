# VectorDBZ

VectorDBZ is a compact, evidence-first AI information aggregation platform.
It collects thousands of daily records from code, model, paper, news, Reddit,
and job-market sources, then reduces them into a small set of cited signals
that can be reviewed, reported, and queried.

The project is intentionally smaller than a full research portal. The target is
not another noisy feed. The target is a maintainable daily intelligence desk:
fresh source health, strict ranking, reusable evidence, and answers that point
back to the records they used.

Repository: `https://github.com/DavidZhu258/vectordbz`

## Current Release Line

- `v1.0` is the clean baseline imported from the earlier workspace. It keeps the
  historical UI/application code and a safe subset of v2 harness files.
- `v2.0` is the evidence-first backend harness: source-aware ingestion,
  ClickHouse/Qdrant storage, resumable long tasks, cited Q&A, deployment
  profiles, and server-safe runtime configuration.

## What v1.0 Got Wrong

The first workspace was useful for exploration, but it mixed too many concerns:

- Product code, local operations, deployment experiments, caches, generated
  archives, screenshots, and external cloned repositories lived side by side.
- Documentation still described a generic desktop vector database client, which
  made the actual information platform unclear.
- Some operational paths assumed local Windows folders or server-specific
  secrets, making independent deployment fragile.
- Source records could collapse into undifferentiated "news", so ranking could
  overfit to volume instead of source quality.
- Long-running work was hard to resume cleanly after a crash or provider limit.
- LLM outputs were asked to do too much: summarize, rank, and explain without a
  deterministic evidence contract in front of them.

v1.0 is therefore kept as a tagged baseline, not as the architecture we want to
grow.

## What v2.0 Changes

v2.0 narrows the system around a few durable primitives:

- Source-aware article rows in ClickHouse `analytics_v2.articles`.
- Vector retrieval in Qdrant `articles_v2`.
- Explicit source taxonomy for GitHub, Hugging Face, Reddit, papers, jobs, and
  news.
- Deterministic report contracts before LLM narration.
- Evidence payloads with source URL, source type, collected time, score, quote,
  and inclusion reason.
- Ask-with-citations API responses that can say "not enough evidence" instead
  of guessing.
- Health and checkpoint state in `analytics_v2.pipeline_state`.
- Resumable `long_task_runner` phases for collection, embedding, rerank, and
  trend report generation.
- Environment-only secrets. Provider keys, database passwords, SSH credentials,
  and PATs must never be committed.
- Deployment profiles for independent server operation in US/HK/153-style
  environments.

## Architecture

```text
collectors
  -> ClickHouse analytics_v2.articles
  -> embedding worker
  -> Qdrant articles_v2
  -> rerank worker
  -> deterministic report contract
  -> LLM narrative and cited Q&A
  -> FastAPI v2 API for the reused UI
```

Core modules live in `vectordbz_v2/`. Tests live in `tests/vectordbz_v2/`.
Deployment assets live in `deploy/vectordbz_v2/`; environment templates live in
`profiles/`.

## Local Verification

```powershell
python -m pytest tests\vectordbz_v2 -q
python -m vectordbz_v2.init_schema
python -m vectordbz_v2.test_smoke
python -m vectordbz_v2.collector_health --limit 1
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

## Deployment

The v2 folder must be deployable as a clean checkout or archive. A server should
only need:

- a clean copy of this repository,
- `deploy/vectordbz_v2/requirements.txt`,
- one profile copied from `profiles/*.env.example`,
- server-only secrets written to `/etc/vectordbz/v2.env`,
- ClickHouse and Qdrant reachable from that environment.

Never deploy from an unreviewed local working tree. Deploy a commit or tag that
has passed tests and a secret scan.

## GitHub Hygiene

Before every public push:

- scan tracked files for provider keys, PATs, database passwords, SSH material,
  `.env` files, archives, caches, and generated stores;
- keep GitHub Actions permissions minimal, especially `GITHUB_TOKEN`;
- avoid committing large generated artifacts such as `node_modules`, `.next`,
  vector stores, screenshots, and backup archives;
- rotate any secret that ever appears in a commit before considering history
  cleanup;
- enable GitHub secret scanning and push protection on the repository.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [v2 Phase Plan](docs/vectordbz_v2_phase_plan.md)
- [v2 Harness Execution Plan](docs/vectordbz_v2_harness_execution_plan.md)
- [v2 Minimal Product Harness](docs/vectordbz_v2_minimal_product_harness.md)
- [Source Onboarding Guide](docs/ADDING_A_DATABASE.md)
