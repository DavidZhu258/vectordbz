from vectordbz_v2 import config, db


class _CommandClient:
    def __init__(self):
        self.commands = []

    def command(self, sql):
        self.commands.append(sql)


def test_ensure_clickhouse_schema_creates_database_and_runtime_tables(monkeypatch):
    client = _CommandClient()
    calls = []

    def fake_get_client(**kwargs):
        calls.append(kwargs)
        return client

    monkeypatch.setattr(db.clickhouse_connect, "get_client", fake_get_client)

    result = db.ensure_clickhouse_schema()

    assert calls[0]["database"] == "default"
    assert result == {"database": config.CLICKHOUSE_DB, "commands": 5}
    joined = "\n".join(client.commands)
    assert f"CREATE DATABASE IF NOT EXISTS {config.CLICKHOUSE_DB}" in joined
    for table in ["articles", "pipeline_state", "rerank_cache", "trend_reports"]:
        assert f"CREATE TABLE IF NOT EXISTS {config.CLICKHOUSE_DB}.{table}" in joined


class _Response:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected status: {self.status_code}")


def test_ensure_qdrant_collection_creates_collection_and_payload_indexes(monkeypatch):
    puts = []

    monkeypatch.setattr(db._requests, "get", lambda *args, **kwargs: _Response(404))
    monkeypatch.setattr(
        db._requests,
        "put",
        lambda url, **kwargs: puts.append((url, kwargs["json"])) or _Response(200),
    )
    monkeypatch.setattr(db, "_qdrant_base", None)
    monkeypatch.setattr(db, "_qdrant_headers", None)

    result = db.ensure_qdrant_collection()

    assert result["collection"] == config.QDRANT_COLLECTION
    assert result["created"] is True
    assert result["payload_indexes"] == ["collected_at", "source_type", "sub_source"]
    assert puts[0][1]["vectors"]["size"] == config.EMBEDDING_DIMENSIONS
    index_fields = [body["field_name"] for _, body in puts[1:]]
    assert index_fields == ["source_type", "sub_source", "collected_at"]
