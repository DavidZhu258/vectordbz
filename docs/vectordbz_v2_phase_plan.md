# VectorDBZ v2.0 Phase Plan

> Updated: 2026-04-28

## Phase 1 Baseline

Status: passed with gaps fixed.

- `analytics_v2` tables exist: `articles`, `pipeline_state`, `rerank_cache`, `trend_reports`.
- Qdrant `articles_v2` is green, 512d, cosine, scalar quantization enabled.
- The original script-style checks did not provide pytest coverage. v2 now has a pytest harness under `tests/vectordbz_v2/`.

## Phase 2 Current Scope

Goal: prove the v2 shape before any large ingestion.

Implemented and tested:

- Source taxonomy keeps GitHub, HF models/datasets/spaces, Reddit, papers, jobs, and generic news separate.
- Digest builder caps each source to Top 5 and global output to Top 10 while preserving source diversity.
- Paper tiering recognizes A* and A venues/ranks and separates top venue papers from generic preprints.
- Job market is a critical source. If job crawling succeeds but finds zero recent jobs, the report is still publishable and records `job_market:no_recent_jobs` as a market signal.
- Phase harness distinguishes `ok`, `degraded`, and `failed` runs.
- LLM JSON parsing tolerates markdown fences, preambles, and trailing text.
- Embedding worker now has a bounded failure budget and will not loop forever when providers fail.
- Migration row mappers reject invalid paper IDs and create readable Reddit fallback titles.
- Report contract builder creates deterministic pre-LLM output with curated papers and job opportunity directions.
- Job directions recover weak signals from `source_url` slugs when V1 job titles/skills are incomplete.
- Trend analyzer now builds the LLM prompt from a deterministic report contract instead of raw rerank rows, and invalid LLM JSON cleanly exhausts retries/fallbacks instead of crashing.
- V1 migration pagination uses bounded pages for both full and limited migrations, avoiding repeated tail reads.
- Unit-testable imports no longer depend on live provider/database clients being invoked.

Live mini-run:

- Migrated small samples from V1 into `analytics_v2.articles`.
- Verified digest categories: `job_market`, `hf_model`, `reddit_subtrend`, `news`, `paper_candidate`.
- Verified report contract over live samples: job direction recovered as `infra`; no paper entered curated best-paper output because the current mini-sample has no A*/A venue or high-signal preprint metadata.
- Qdrant remains at 0 vectors until explicit embedding provider keys are configured.

## v1.0 Failure Points Avoided

v1.0 was useful as an exploratory workspace, but it made several mistakes that
v2.0 must not repeat:

- It mixed product code with local operations, caches, generated artifacts,
  deployment experiments, and external cloned projects.
- It let copied documentation describe a generic vector database desktop client
  instead of the actual information aggregation platform.
- It relied too much on local/server-specific assumptions, including paths and
  runtime secrets that should live outside git.
- It did not make evidence and answerability the center of the product.

- No unbounded Chroma-dependent nightly path for v2 core tests.
- No mixed "everything is news" reporting layer; canonical categories are code-level rules.
- No unlimited source flood; TopN caps are enforced before LLM summarization.
- No silent LLM JSON parse collapse from markdown-wrapped output.
- No infinite embedding retry loop when all providers fail.
- No invalid empty IDs/titles entering the v2 signal digest.

## Target Data Sources

- Hugging Face: models, datasets, spaces. Rank by trending score, downloads, likes, task tags, and recency.
- GitHub: repositories. Rank by stars, forks, topic fit, freshness, and cross-source confirmation.
- Reddit: subreddit-level trend posts. Rank by score, comments, upvote ratio, and repeated theme presence.
- Papers: A* and A venues first, then high-signal preprints. Keep papers as a curated list, not a bulk feed.
- Jobs: critical market signal. Rank by recent openings, skill match, salary/company signal, and source freshness.

## Output Contract

Daily and weekly reports should expose:

- Top 5 per source category.
- Top 10 strongest cross-source signals.
- Best papers, separated by A*/A and preprint candidates.
- Job opportunity directions, including "no recent jobs" as a negative market signal.
- Source health state: `ok`, `degraded`, or `failed`, with blocking sources named explicitly.

Current deterministic report payload keys:

- `source_counts`
- `source_health`
- `top_by_source`
- `strongest_signals`
- `best_papers.top_venue`
- `best_papers.preprints`
- `job_opportunity_directions`

## Next Phases

### Phase 3: Source Collectors

- Move GitHub/HF collection from generic `analytics.news` into source-aware V2 records.
- Status: started. `migrate_news` now classifies GitHub rows as `github_repo` and HF rows as `hf_model`/`hf_dataset`/`hf_space` based on source metadata and URLs.
- Status: wired. `collectors.py` can collect GitHub repositories and HF models/datasets/spaces into source-aware V2 article rows. HF uses `sort=likes7d&direction=-1`, matching the current public API behavior.
- Status: wired/tested. `collectors.py` now also exposes V1-backed news, Reddit, jobs, and papers collectors, so every article-producing source has a V2-local entrypoint.
- Status: wired/tested. `service_registry.py` records the 153 Dagu services (`crawl`, `jobspy`, `ever_jobs`, `foorilla`, `news_rss`, `pyalex`, `reddit_discovery`, `finance`, `health_report`) plus local `github_hf_live`; finance and health are tracked as operational/non-article services.
- Status: verified. `python -m vectordbz_v2.collector_health --limit 1` dry-runs GitHub, HF, news, Reddit, jobs, and papers without writing rows and returned `state=ok`.
- Status: wired/tested. `run_source_collectors` applies source-level retry/backoff, isolates optional source failures, and records aggregate fetch/accept/attempt/error details.
- Status: wired/tested. Reddit refresh reads recent V1 subreddit posts and labels rows with `metadata.sub_source=reddit:<subreddit>`.
- Status: wired/tested. Paper rows are enriched with known venue rank metadata before V2 scoring/reporting.
- Status: wired/tested. Job rows enter V2 as critical market-source records with `metadata.critical_source=true`.
- Status: fixed. V1 ClickHouse datetime/date values from Reddit and jobs now parse correctly instead of calling the string-only timestamp path.

### Phase 4: Ranking and Report Generation

- Use `build_signal_digest` before every LLM call.
- Use `build_report_contract` as the pre-LLM payload; the LLM should narrate and cross-reference this payload, not re-rank raw feeds.
- Status: started. `trend_analyzer` converts reranked rows into a capped source digest and sends `build_report_contract` output to the LLM.
- Status: started. Embed and rerank workers preserve `source_url` and Qdrant payload metadata so report contracts can carry source evidence.
- Status: fixed. DeepInfra Qwen3-Reranker calls now use the official `queries: [...]` request body; the previous singular `query` body caused live rerank connectivity failures.
- Live mini-run status: embedded 16 unique sample records into Qdrant, reranked 32 theme/source rows, and generated one daily trend report via DeepInfra after one transient 429 retry.
- Long-task status: `python -m vectordbz_v2.long_task_runner` runs embedding, rerank, and trend report phases as one bounded pipeline. The rerank cache is now idempotent per `(run_date, sub_source)` and repeated long-task runs keep `rerank_cache FINAL` at 32 rows for the two-theme sample.
- Full bounded run status: with `--collect-live --github-limit 2 --hf-limit-per-type 1`, the pipeline collected 5 source-aware rows, embedded them, reranked 40 rows, generated a report, and stored both `contract` and `narrative` in `trend_reports.report_json`.
- Full Phase3/4/5 bounded run status: with `--collect-live --github-limit 2 --hf-limit-per-type 1 --embed-max 40`, the pipeline collected 35 rows across GitHub/HF/Reddit/jobs/papers, embedded 40 rows, reranked 40 rows, generated one daily report, and ended `state=ok`.
- Historical 2026-04-01 window run status: a bounded per-day sample from 2026-04-01 through 2026-04-28 inserted 1,656 new unique V2 articles, embedded all 1,700 final rows, reranked 180 theme rows, and generated a daily report with `contract` and `narrative`.
- Historical backfill status: `python -m vectordbz_v2.source_backfill --start 2026-04-01 --end 2026-04-28 --per-day-limit 20 --dry-run` selects 1,727 rows across papers/news/Reddit/jobs. `--per-day-limit 0` now uses day-by-day pagination for full backfills instead of loading the whole window at once.
- Feed the LLM only capped, categorized, evidence-rich signals.
- Persist both raw digest JSON and LLM narrative JSON.
- Status: wired. Trend reports now persist `{"contract": ..., "narrative": ...}`.
- Status: wired/tested. `validate_report_payload` regression tests require both deterministic `contract` and LLM `narrative` schema keys.

### Phase 5: Server Operations

- Add per-source health writes to `pipeline_state`.
- Status: started. `ch_insert_source_health` writes aggregate and per-source health records to `pipeline_state` using stable keys.
- Status: wired. `run_trend_analyzer` persists source health when provided; the live mini-run wrote aggregate, embedding, rerank, and trend-report health records to `pipeline_state`.
- Status: wired. The long-task runner writes final phase health after all phases and stops before later phases if a critical phase fails.
- Status: wired/tested. Bounded retries with exponential backoff are covered for transient source failures.
- Status: wired/tested. Per-source failure isolation keeps optional failures degraded and critical failures blocking.
- Status: wired/tested. Watchdog alert derivation flags repeated critical failures and empty critical-source fetches.
- Status: verified. Article writes remain idempotent by `(source_type, source_id)` and rerank writes have zero duplicate `(run_date, sub_source, source_type, source_id)` keys in `FINAL`.
- Remote inspection note: SSH to the 153 server was attempted, but `connect.cqa1.seetacloud.com:12947` currently resolves to the Clash fake-ip range and closes before SSH banner exchange. V2 service coverage is therefore based on the local runbook inventory plus local ClickHouse table verification until direct SSH is restored.
