"""
VectorDBZ V2 — Database Connectors
ClickHouse (analytics_v2) + Qdrant unified access layer.
"""
import json
import logging
from datetime import date, datetime, timezone
from typing import Any

import clickhouse_connect
from qdrant_client import QdrantClient, models

from . import config

logger = logging.getLogger("vectordbz_v2.db")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ClickHouse
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_ch_client = None


CLICKHOUSE_SCHEMA_COMMANDS = [
    f"CREATE DATABASE IF NOT EXISTS {config.CLICKHOUSE_DB}",
    f"""
    CREATE TABLE IF NOT EXISTS {config.CLICKHOUSE_DB}.articles
    (
        `source_type` LowCardinality(String),
        `source_id` String,
        `published_at` DateTime64(3) DEFAULT toDateTime64('1970-01-01', 3),
        `collected_at` DateTime64(3) DEFAULT now64(3),
        `title` String,
        `content` String DEFAULT '',
        `author` String DEFAULT '',
        `source_url` String DEFAULT '',
        `metadata` String DEFAULT '{{}}',
        `is_embedded` UInt8 DEFAULT 0,
        `embed_model` LowCardinality(String) DEFAULT '',
        `updated_at` DateTime DEFAULT now()
    )
    ENGINE = ReplacingMergeTree(updated_at)
    PARTITION BY (source_type, toYYYYMM(collected_at))
    ORDER BY (source_type, source_id)
    SETTINGS index_granularity = 8192
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {config.CLICKHOUSE_DB}.pipeline_state
    (
        `key` String,
        `value_json` String DEFAULT '{{}}',
        `updated_at` DateTime DEFAULT now()
    )
    ENGINE = ReplacingMergeTree(updated_at)
    ORDER BY key
    SETTINGS index_granularity = 8192
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {config.CLICKHOUSE_DB}.rerank_cache
    (
        `run_date` Date,
        `source_type` LowCardinality(String),
        `sub_source` LowCardinality(String) DEFAULT '',
        `rank` UInt32,
        `source_id` String,
        `title` String,
        `source_url` String DEFAULT '',
        `rerank_score` Float32,
        `llm_summary` String DEFAULT '',
        `model_used` LowCardinality(String) DEFAULT 'Qwen/Qwen3-Reranker-0.6B',
        `created_at` DateTime DEFAULT now()
    )
    ENGINE = ReplacingMergeTree(created_at)
    PARTITION BY toYYYYMM(run_date)
    ORDER BY (run_date, source_type, sub_source, rank)
    SETTINGS index_granularity = 8192
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {config.CLICKHOUSE_DB}.trend_reports
    (
        `period_type` LowCardinality(String),
        `period_date` Date,
        `report_json` String,
        `model_used` LowCardinality(String),
        `token_cost` UInt32 DEFAULT 0,
        `created_at` DateTime DEFAULT now()
    )
    ENGINE = ReplacingMergeTree(created_at)
    PARTITION BY toYear(period_date)
    ORDER BY (period_type, period_date)
    SETTINGS index_granularity = 8192
    """,
]


QDRANT_PAYLOAD_INDEXES = {
    "source_type": "keyword",
    "sub_source": "keyword",
    "collected_at": "datetime",
}


def get_ch() -> clickhouse_connect.driver.Client:
    """Lazy singleton ClickHouse client."""
    global _ch_client
    if _ch_client is None:
        _ch_client = clickhouse_connect.get_client(
            host=config.CLICKHOUSE_HOST,
            port=config.CLICKHOUSE_HTTP_PORT,
            database=config.CLICKHOUSE_DB,
            username=config.CLICKHOUSE_USER,
            password=config.CLICKHOUSE_PASSWORD,
        )
        logger.info(f"ClickHouse connected: {config.CLICKHOUSE_HOST}:{config.CLICKHOUSE_HTTP_PORT}/{config.CLICKHOUSE_DB}")
    return _ch_client


def get_ch_v1() -> clickhouse_connect.driver.Client:
    """ClickHouse client for V1 analytics (read-only migration)."""
    return clickhouse_connect.get_client(
        host=config.CLICKHOUSE_HOST,
        port=config.CLICKHOUSE_HTTP_PORT,
        database=config.CLICKHOUSE_V1_DB,
        username=config.CLICKHOUSE_USER,
        password=config.CLICKHOUSE_PASSWORD,
    )


def ensure_clickhouse_schema() -> dict:
    """Create the analytics_v2 database and tables if they do not exist."""
    client = clickhouse_connect.get_client(
        host=config.CLICKHOUSE_HOST,
        port=config.CLICKHOUSE_HTTP_PORT,
        database="default",
        username=config.CLICKHOUSE_USER,
        password=config.CLICKHOUSE_PASSWORD,
    )
    for command in CLICKHOUSE_SCHEMA_COMMANDS:
        client.command(command)
    logger.info("ClickHouse schema ensured: %s", config.CLICKHOUSE_DB)
    return {"database": config.CLICKHOUSE_DB, "commands": len(CLICKHOUSE_SCHEMA_COMMANDS)}


def ch_insert_articles(rows: list[dict]) -> int:
    """
    Insert articles into analytics_v2.articles.
    Uses INSERT with ReplacingMergeTree — duplicates auto-deduplicated.
    Returns number of rows inserted.
    """
    if not rows:
        return 0

    columns = [
        "source_type", "source_id", "published_at", "collected_at",
        "title", "content", "author", "source_url", "metadata",
    ]

    data = []
    for r in rows:
        data.append([
            r["source_type"],
            r["source_id"],
            r.get("published_at", datetime(1970, 1, 1, tzinfo=timezone.utc)),
            r.get("collected_at", datetime.now(timezone.utc)),
            r.get("title", ""),
            r.get("content", ""),
            r.get("author", ""),
            r.get("source_url", ""),
            json.dumps(r.get("metadata", {}), ensure_ascii=False),
        ])

    client = get_ch()
    client.insert("articles", data, column_names=columns)
    logger.info(f"Inserted {len(data)} articles (source_type={rows[0]['source_type']})")
    return len(data)


def ch_get_unembedded(limit: int = 1000) -> list[dict]:
    """Get articles that haven't been embedded in Qdrant yet."""
    client = get_ch()
    result = client.query(
        "SELECT source_type, source_id, title, content, source_url, metadata "
        "FROM articles WHERE is_embedded = 0 "
        f"ORDER BY collected_at DESC LIMIT {limit}"
    )
    return [
        {
            "source_type": row[0],
            "source_id": row[1],
            "title": row[2],
            "content": row[3],
            "source_url": row[4],
            "metadata": _parse_metadata(row[5]),
        }
        for row in result.result_rows
    ]


def _parse_metadata(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def ch_mark_embedded(keys: list[tuple[str, str]], model_name: str):
    """Mark articles as embedded. keys = [(source_type, source_id), ...]"""
    if not keys:
        return
    client = get_ch()
    # Use ALTER TABLE UPDATE for ReplacingMergeTree
    pairs = ", ".join(
        f"('{st}', '{sid}')" for st, sid in keys
    )
    client.command(
        f"ALTER TABLE articles UPDATE is_embedded = 1, embed_model = '{model_name}' "
        f"WHERE (source_type, source_id) IN ({pairs})"
    )
    logger.info(f"Marked {len(keys)} articles as embedded (model={model_name})")


def ch_insert_rerank(rows: list[dict]) -> int:
    """Insert rerank results into rerank_cache."""
    if not rows:
        return 0
    columns = [
        "run_date", "source_type", "sub_source", "rank",
        "source_id", "title", "source_url", "rerank_score",
        "llm_summary", "model_used",
    ]
    data = [[r.get(c, "") for c in columns] for r in rows]
    client = get_ch()
    _delete_existing_rerank_rows(client, rows)
    client.insert("rerank_cache", data, column_names=columns)
    logger.info(f"Inserted {len(data)} rerank records for {rows[0].get('run_date')}")
    return len(data)


def _delete_existing_rerank_rows(client: clickhouse_connect.driver.Client, rows: list[dict]) -> None:
    pairs = sorted({
        (str(row.get("run_date")), str(row.get("sub_source") or ""))
        for row in rows
        if row.get("run_date")
    })
    if not pairs:
        return

    clauses = [
        f"(run_date = toDate('{_escape_ch_string(run_date)}') "
        f"AND sub_source = '{_escape_ch_string(sub_source)}')"
        for run_date, sub_source in pairs
    ]
    client.command(
        "ALTER TABLE rerank_cache DELETE WHERE "
        + " OR ".join(clauses)
        + " SETTINGS mutations_sync = 1"
    )


def _escape_ch_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def ch_insert_trend_report(report: dict) -> None:
    """Insert a trend report."""
    get_ch().insert("trend_reports", [[
        report["period_type"],
        report["period_date"],
        json.dumps(report["report_json"], ensure_ascii=False),
        report["model_used"],
        report.get("token_cost", 0),
    ]], column_names=[
        "period_type", "period_date", "report_json", "model_used", "token_cost",
    ])
    logger.info(f"Inserted trend report: {report['period_type']} {report['period_date']}")


def ch_insert_source_health(source_health: dict, run_date: date | None = None) -> int:
    """Persist aggregate and per-source health state into pipeline_state."""
    run_date = run_date or date.today()
    timestamp = datetime.now(timezone.utc)
    rows = [
        [
            f"source_health:{run_date.isoformat()}",
            json.dumps(source_health, ensure_ascii=False),
            timestamp,
        ]
    ]
    for source in source_health.get("sources", []):
        source_name = str(source.get("source") or "").strip()
        if not source_name:
            continue
        rows.append([
            f"source_health:{run_date.isoformat()}:{source_name}",
            json.dumps(source, ensure_ascii=False),
            timestamp,
        ])

    get_ch().insert(
        "pipeline_state",
        rows,
        column_names=["key", "value_json", "updated_at"],
    )
    logger.info(f"Inserted {len(rows)} source health state records for {run_date}")
    return len(rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Qdrant (REST API via requests — httpx/qdrant-client has 502 bug on Windows Docker)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import requests as _requests

_qdrant_base = None
_qdrant_headers = None


def _qdrant_url(path: str) -> str:
    global _qdrant_base, _qdrant_headers
    if _qdrant_base is None:
        _qdrant_base = f"http://{config.QDRANT_HOST}:{config.QDRANT_PORT}"
        _qdrant_headers = {"Content-Type": "application/json"}
        if config.QDRANT_API_KEY:
            _qdrant_headers["api-key"] = config.QDRANT_API_KEY
        logger.info(f"Qdrant REST: {_qdrant_base}")
    return f"{_qdrant_base}{path}"


def ensure_qdrant_collection() -> dict:
    """Create the Qdrant collection and payload indexes if needed."""
    collection_path = f"/collections/{config.QDRANT_COLLECTION}"
    resp = _requests.get(_qdrant_url(collection_path), headers=_qdrant_headers, timeout=10)
    created = False
    if resp.status_code == 404:
        body = {
            "vectors": {
                "size": config.EMBEDDING_DIMENSIONS,
                "distance": "Cosine",
            },
            "hnsw_config": {
                "m": 16,
                "ef_construct": 128,
            },
            "quantization_config": {
                "scalar": {
                    "type": "int8",
                    "quantile": 0.99,
                    "always_ram": True,
                }
            },
        }
        create_resp = _requests.put(
            _qdrant_url(collection_path),
            headers=_qdrant_headers,
            json=body,
            timeout=30,
        )
        create_resp.raise_for_status()
        created = True
    else:
        resp.raise_for_status()

    for field_name, field_schema in QDRANT_PAYLOAD_INDEXES.items():
        index_resp = _requests.put(
            _qdrant_url(f"{collection_path}/index"),
            headers=_qdrant_headers,
            json={"field_name": field_name, "field_schema": field_schema},
            timeout=30,
        )
        index_resp.raise_for_status()

    logger.info("Qdrant collection ensured: %s", config.QDRANT_COLLECTION)
    return {
        "collection": config.QDRANT_COLLECTION,
        "created": created,
        "payload_indexes": sorted(QDRANT_PAYLOAD_INDEXES),
    }


def ensure_runtime_schema() -> dict:
    """Ensure ClickHouse and Qdrant runtime schema for an independent deploy."""
    return {
        "clickhouse": ensure_clickhouse_schema(),
        "qdrant": ensure_qdrant_collection(),
    }


def qdrant_upsert(points: list[dict]) -> None:
    """
    Upsert points into Qdrant via REST API.
    Each point: {"id": str, "vector": [...], "payload": {...}}
    """
    if not points:
        return

    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        payload = {
            "points": [
                {
                    "id": p["id"],
                    "vector": p["vector"],
                    "payload": p.get("payload", {}),
                }
                for p in batch
            ]
        }
        resp = _requests.put(
            _qdrant_url(f"/collections/{config.QDRANT_COLLECTION}/points"),
            headers=_qdrant_headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()

    logger.info(f"Qdrant upserted {len(points)} points")


def qdrant_search(
    query_vector: list[float],
    source_types: list[str] | None = None,
    days: int = 7,
    limit: int = 50,
) -> list[dict]:
    """
    Semantic search in Qdrant with optional source_type and time filtering.
    Returns list of {id, score, payload}.
    """
    must_conditions = []

    if source_types:
        must_conditions.append({
            "key": "source_type",
            "match": {"any": source_types},
        })

    if days > 0:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        must_conditions.append({
            "key": "collected_at",
            "range": {"gte": cutoff},
        })

    body = {
        "vector": query_vector,
        "limit": limit,
        "with_payload": True,
        "params": {"hnsw_ef": 128, "exact": False},
    }
    if must_conditions:
        body["filter"] = {"must": must_conditions}

    resp = _requests.post(
        _qdrant_url(f"/collections/{config.QDRANT_COLLECTION}/points/search"),
        headers=_qdrant_headers,
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    return [
        {
            "id": str(r["id"]),
            "score": r["score"],
            "payload": r.get("payload", {}),
        }
        for r in data.get("result", [])
    ]


def qdrant_collection_info() -> dict:
    """Get collection info (for diagnostics)."""
    resp = _requests.get(
        _qdrant_url(f"/collections/{config.QDRANT_COLLECTION}"),
        headers=_qdrant_headers,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["result"]
