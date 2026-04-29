# VectorDBZ v2.0 Minimal Product Harness

> Updated: 2026-04-28  
> Goal: small, maintainable, high-value intelligence aggregation with evidence-grounded Q&A.

## Positioning

VectorDBZ v2.0 should not become another heavy research portal. The sharper product is a compact daily intelligence desk: collect a few thousand records, collapse them into a small number of verified signals, preserve evidence, and answer questions with citations. The principle is "less feed, more judgment": fewer screens, fewer knobs, fewer LLM calls, more source freshness, evidence spans, and clear next actions.

The UI should reuse v1.0 dashboard patterns. Do not rebuild a new product surface until the backend proves that it can produce a small set of trustworthy daily results. The first screen should remain operational: date, source health, top signals, evidence, Q&A, and backfill status.

## Exa Research Takeaways

Elicit's useful lesson is workflow discipline, not academic verticality. Its systematic review flow asks a question, gathers sources, screens papers against explicit criteria, extracts structured fields, and backs generated claims with sentence-level citations. It also keeps humans in control through editable screening and extraction criteria. For VectorDBZ, the equivalent is: every daily signal must have inclusion criteria, extraction fields, source quotes, and a reason it survived filtering. Sources: [Elicit systematic reviews](https://elicit.com/solutions/literature-review), [Elicit workflow guide](https://support.elicit.com/en/articles/1418881).

Recent Reddit and open-source research shows the pain points we should directly avoid. Agent-framework discussions on r/LocalLLaMA repeatedly mention heavyweight frameworks, poor failure handling, tool-call latency, context truncation, and stale comparisons. MCP discussions praise simple interfaces but warn that too many tools inflate tokens and latency; precise schemas matter more than marketing descriptions. Long-running agent users complain that crashes or context overflows lose the whole run unless state is persisted. SaaS/product discussions repeat that users do not lack information; they lack prioritization and context-specific next steps. Sources: [44 agent framework analysis thread](https://www.reddit.com/r/LocalLLaMA/comments/1r84o6p/i_did_an_analysis_of_44_ai_agent_frameworks/), [MCP experience thread](https://www.reddit.com/r/LocalLLaMA/comments/1r3mdqe/anyone_else_building_mcp_servers_whats_your/), [long-running state thread](https://www.reddit.com/r/LocalLLaMA/comments/1s3gewc/the_vram_crash_tax_how_are_you_persisting_state/), [SaaS prioritization thread](https://www.reddit.com/r/SaaS/comments/1rjpsjg/2_failed_products_0_customers_and_how_im_trying.json).

Open-source intelligence projects such as agents-radar and ai-pulse validate our source mix: GitHub, Hugging Face, arXiv/papers, Reddit, HN/news, Product Hunt, and official AI vendor updates. Their weakness for our use case is that they still tend toward digest volume. VectorDBZ should use them as source inspiration, not as a UI model. We need fewer surfaced items, stronger dedupe, better source health, and a durable ClickHouse/Qdrant evidence layer. Sources: [agents-radar](https://github.com/duanyytop/agents-radar/), [ai-pulse](https://github.com/hugodendievel-cmd/ai-pulse).

## Product Rules

1. Curate before summarizing. Dedupe, cluster, score, and exclude low-signal items before any LLM call.
2. Evidence table first, narrative second. Store source URL, timestamp, source type, quote/span, score, and reason for inclusion.
3. Q&A must be humble. If evidence is old, thin, or contradictory, the answer says so rather than filling gaps.
4. Reports must be small. Daily output should be 5 to 12 signals, not a feed dump.
5. LLM use must be budgeted. Embedding and rerank can run broadly; generation only runs on compact clusters.
6. The system must survive partial failure. Optional sources degrade the run; critical sources block publish only when freshness or evidence is insufficient.
7. Every long task is resumable. Backfill, collection, embedding, rerank, and report generation persist progress.

## Minimal Architecture

```text
source adapters
  -> raw landing in ClickHouse
  -> normalization + source-specific identity
  -> dedupe and cluster
  -> evidence ledger
  -> curated articles in analytics_v2
  -> batch embedding queue
  -> Qdrant articles_v2
  -> hybrid retrieval
  -> rerank
  -> answer/report composer
  -> reused v1 dashboard UI
```

This keeps v2 independent while staying compatible with v1 UI. The backend owns the new intelligence contract; the frontend consumes compact endpoints.

## Harness Tasks

### H1: Git and Release Baseline

The current workspace is already a git repository with remote `https://github.com/vectordbz/vectordbz.git`. Do not reinitialize it. Create a dedicated release branch only after the v2 implementation scope is approved, then commit only scoped v2 files. Because the worktree currently contains many unrelated modifications and untracked directories, deployment must never use "whatever is in the workspace". Deployment must use a clean checkout or a tagged commit.

Acceptance:
- `git status` reviewed before each commit.
- v2 files, tests, docs, deploy scripts are committed together.
- no provider tokens, passwords, or server secrets in git.

### H2: Source Curation and Reddit Scope

Add a small configurable source registry. Default Reddit sources should be narrow and useful:
- AI/agent: `LocalLLaMA`, `AI_Agents`, `MachineLearning`, `LLMDevs`, `artificial`.
- Product/market: `SaaS`, `startups`, `ProductManagement`.
- Data/practice: `datascience`, `datasets`, `MLQuestions`.

Each subreddit must have a purpose, quality threshold, and exclusion rule. Do not surface generic hype unless it is confirmed by GitHub/HF/jobs/news.

Acceptance:
- source registry has per-source freshness, threshold, and failure state.
- reports explain why a Reddit item survived.
- repeated posts about the same tool collapse into one signal.

### H3: Elicit-Style Evidence Extraction

Add a compact extraction schema per signal:
- `claim`: one-sentence finding.
- `why_now`: recency or velocity reason.
- `evidence_spans`: 1 to 5 cited snippets.
- `counter_evidence`: contradiction or caveat.
- `action`: what a user should inspect next.
- `confidence`: high, medium, low with reason.

This schema should power both daily reports and Q&A. It should not be a giant ontology.

Acceptance:
- every answer and report item links to evidence IDs.
- no source span means no confident claim.
- stale evidence is visibly marked.

### H4: Cost and Performance Guardrails

For daily thousands of records, run:
- dedupe before embedding.
- embedding only for new canonical records.
- rerank only on candidate clusters.
- LLM only on top clusters and user Q&A.
- cache by content hash and query hash.

Acceptance:
- 5,000 daily raw records complete collection, dedupe, embedding, rerank, and report in under 30 minutes on one server.
- daily generation stays under a fixed LLM-call budget.
- long-task runner can resume after interruption.

### H5: HK/US/153 Deployment

Deployment target is two production-style nodes: 153 crawler server and US server. Use skill-provided server inventory at deploy time, but never commit credentials. HK remains useful for dashboard/Reddit/ClickHouse tunnel checks, but the user asked for 153 and US deployment.

Each server must support:
- clean checkout from git.
- environment-only secrets.
- local `analytics_v2` initialization.
- Qdrant startup or configured remote Qdrant.
- `collector_health`, `source_backfill`, `long_task_runner`, and `test_smoke`.
- systemd service or equivalent runner.

Acceptance:
- clean checkout deploy succeeds without local untracked files.
- 2026-04-01 backfill can run to completion or resume by date.
- both servers generate a daily report and answer a cited question.

### H6: UI Reuse

Reuse v1 dashboard layout. Add only minimal v2 views:
- Source Health.
- Daily Signals.
- Evidence Drawer.
- Ask With Citations.
- Backfill/Runner Status.

Avoid a new landing page, new visual system, or heavy dashboard redesign. The UI should make the backend's judgment visible, not create more surfaces to maintain.

## Deployment Gate

Do not deploy until all are true:
- `python -m pytest tests\vectordbz_v2 -q` passes.
- `python -m vectordbz_v2.test_smoke` passes.
- token/secret scan is clean.
- backfill dry run from 2026-04-01 succeeds.
- one bounded live run produces source health, vectors, rerank rows, report, and cited Q&A.
- deployment script uses a clean git ref.

## Product North Star

VectorDBZ should feel like a calm analyst, not a louder feed reader. It should tell the user what changed, why it matters, what evidence supports it, what is uncertain, and what to inspect next. The moat is not source count; it is compact, current, cross-source judgment with evidence.
