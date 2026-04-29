# Adding a Source Connector

This file keeps its historical path for compatibility, but v2.0 no longer treats
VectorDBZ as a generic "add another vector database" desktop client. New work
should add high-quality information sources to the evidence pipeline.

## Connector Standard

A source connector should answer five questions before code is written:

- What decision can this source improve?
- How fresh does it need to be?
- Which fields become evidence?
- What makes an item high signal?
- What failure state should block publication, degrade the run, or be ignored?

## Required Fields

Every accepted item should map to a v2 article row:

| Field | Meaning |
| --- | --- |
| `source_type` | Canonical source family, such as `github_repo` or `job_market`. |
| `source_id` | Stable id within that source family. |
| `title` | Human-readable title. |
| `content` | Summary or body text used for embedding and rerank. |
| `source_url` | Canonical URL for citation. |
| `metadata` | Structured source-specific facts. |
| `collected_at` | Collection timestamp. |

## Implementation Checklist

- Add or update source rules in `vectordbz_v2/source_registry.py`.
- Add collector code in `vectordbz_v2/collectors.py` or a small helper module.
- Preserve source URL and metadata all the way into ClickHouse and Qdrant.
- Add unit tests under `tests/vectordbz_v2/`.
- Add health behavior to `collector_health` when the source is operationally
  important.
- Add backfill behavior only if historical records are useful and bounded.
- Update report contract tests if the source should appear in daily signals.

## Quality Rules

Prefer narrow, high-value sources over broad feeds. A source is useful when it
adds freshness, confirmation, market signal, or primary evidence. It is not
useful merely because it produces many rows.

## Secrets

API keys, cookies, passwords, and private headers must be read from environment
variables or server-local secret files. Do not add them to examples, tests,
fixtures, screenshots, logs, or markdown.
