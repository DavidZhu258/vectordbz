from vectordbz_v2 import db
from datetime import date


class _QueryResult:
    result_rows = [
        (
            "github_repo",
            "gh-1",
            "owner/repo",
            "Repo content",
            "https://github.com/owner/repo",
            '{"stars": 100}',
        )
    ]


class _Client:
    def query(self, sql):
        self.sql = sql
        return _QueryResult()


def test_ch_get_unembedded_preserves_source_url_and_metadata(monkeypatch):
    client = _Client()
    monkeypatch.setattr(db, "get_ch", lambda: client)

    rows = db.ch_get_unembedded(limit=1)

    assert "source_url" in client.sql
    assert "metadata" in client.sql
    assert rows == [
        {
            "source_type": "github_repo",
            "source_id": "gh-1",
            "title": "owner/repo",
            "content": "Repo content",
            "source_url": "https://github.com/owner/repo",
            "metadata": {"stars": 100},
        }
    ]


class _InsertClient:
    def __init__(self):
        self.inserts = []
        self.commands = []

    def insert(self, table, rows, column_names):
        self.inserts.append((table, rows, column_names))

    def command(self, sql):
        self.commands.append(sql)


def test_ch_insert_source_health_writes_aggregate_and_per_source_state(monkeypatch):
    client = _InsertClient()
    monkeypatch.setattr(db, "get_ch", lambda: client)

    db.ch_insert_source_health(
        {
            "state": "degraded",
            "can_publish": True,
            "sources": [
                {
                    "source": "job_market",
                    "critical": True,
                    "fetch_ok": True,
                    "fetched": 0,
                    "accepted": 0,
                }
            ],
        },
        run_date=date(2026, 4, 28),
    )

    table, rows, columns = client.inserts[0]
    assert table == "pipeline_state"
    assert columns == ["key", "value_json", "updated_at"]
    keys = [row[0] for row in rows]
    assert keys == [
        "source_health:2026-04-28",
        "source_health:2026-04-28:job_market",
    ]
    assert '"state": "degraded"' in rows[0][1]
    assert '"source": "job_market"' in rows[1][1]


def test_ch_insert_rerank_deletes_existing_date_theme_rows_before_insert(monkeypatch):
    client = _InsertClient()
    monkeypatch.setattr(db, "get_ch", lambda: client)

    inserted = db.ch_insert_rerank(
        [
            {
                "run_date": date(2026, 4, 28),
                "source_type": "paper",
                "sub_source": "agent eval",
                "rank": 1,
                "source_id": "paper-1",
                "title": "Paper",
                "source_url": "https://example.com",
                "rerank_score": 0.9,
                "llm_summary": "",
                "model_used": "model",
            }
        ]
    )

    assert inserted == 1
    assert client.commands
    assert "ALTER TABLE rerank_cache DELETE" in client.commands[0]
    assert "toDate('2026-04-28')" in client.commands[0]
    assert "'agent eval'" in client.commands[0]
