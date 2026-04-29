from datetime import date, datetime

from vectordbz_v2 import source_backfill


class _Result:
    def __init__(self, rows):
        self.result_rows = rows


class _FakeClient:
    def __init__(self):
        self.queries = []

    def query(self, sql):
        self.queries.append(sql)
        if "FROM papers" in sql:
            return _Result([
                (
                    "2504.00001",
                    "Agent Benchmarks",
                    "Abstract",
                    "A. Researcher",
                    "cs.AI",
                    "cs.AI",
                    "https://example.com/paper.pdf",
                    date(2026, 4, 1),
                    datetime(2026, 4, 1),
                    10,
                    3,
                    2,
                    "NeurIPS",
                    "conference",
                    "pyalex",
                )
            ])
        if "FROM news" in sql:
            return _Result([
                (
                    "news-1",
                    "AI infra news",
                    "Body",
                    "https://example.com/news",
                    "rss",
                    datetime(2026, 4, 1),
                    datetime(2026, 4, 1),
                    ["ai"],
                    "{}",
                )
            ])
        if "FROM media_reddit_post" in sql:
            return _Result([
                (
                    "rd-1",
                    "Local model deployment",
                    "Body",
                    "https://reddit.com/r/LocalLLaMA/comments/rd-1",
                    "LocalLLaMA",
                    "user",
                    120,
                    30,
                    0.95,
                    datetime(2026, 4, 1),
                )
            ])
        if "FROM jobs" in sql:
            return _Result([
                (
                    "job-1",
                    "RAG Engineer",
                    "Acme",
                    "Remote",
                    "$180k",
                    "Build RAG systems",
                    "https://example.com/job",
                    "jobspy",
                    date(2026, 4, 1),
                    "rag, agents",
                )
            ])
        raise AssertionError(sql)


def test_build_source_query_can_sample_every_day_back_to_april_first():
    sql = source_backfill.build_source_query(
        "papers",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 28),
        per_day_limit=20,
    )

    assert "update_date >= toDate('2026-04-01')" in sql
    assert "update_date <= toDate('2026-04-28')" in sql
    assert "LIMIT 20 BY update_date" in sql


def test_historical_backfill_maps_all_article_sources_and_inserts_batches():
    fake = _FakeClient()
    inserted = []

    result = source_backfill.run_historical_backfill(
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 28),
        per_day_limit=1,
        sources=["papers", "news", "reddit", "jobs"],
        ch_v1=fake,
        insert_articles=lambda rows: inserted.extend(rows) or len(rows),
    )

    assert result["selected_rows"] == {"papers": 1, "news": 1, "reddit": 1, "jobs": 1}
    assert result["articles_inserted"] == 4
    assert {row["source_type"] for row in inserted} == {"paper", "news", "reddit", "job"}
    paper = next(row for row in inserted if row["source_type"] == "paper")
    assert paper["metadata"]["venue"] == "NeurIPS"
    assert paper["metadata"]["venue_rank"] == "A*"


def test_historical_backfill_dry_run_does_not_insert():
    fake = _FakeClient()

    result = source_backfill.run_historical_backfill(
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 28),
        per_day_limit=1,
        sources=["papers"],
        ch_v1=fake,
        insert_articles=lambda rows: (_ for _ in ()).throw(AssertionError("inserted")),
        dry_run=True,
    )

    assert result["articles_selected"] == 1
    assert result["articles_inserted"] == 0


def test_uncapped_historical_backfill_reads_daily_pages():
    class _PagedClient:
        def __init__(self):
            self.queries = []

        def query(self, sql):
            self.queries.append(sql)
            if "OFFSET 0" in sql:
                row = (
                    "news-1",
                    "AI infra news",
                    "Body",
                    "https://example.com/news",
                    "rss",
                    datetime(2026, 4, 1),
                    datetime(2026, 4, 1),
                    ["ai"],
                    "{}",
                )
                return _Result([
                    row,
                    (
                        "news-2",
                        "AI tooling news",
                        "Body",
                        "https://example.com/news-2",
                        "rss",
                        datetime(2026, 4, 1),
                        datetime(2026, 4, 1),
                        ["ai"],
                        "{}",
                    )
                ])
            return _Result([])

    fake = _PagedClient()

    result = source_backfill.run_historical_backfill(
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 1),
        per_day_limit=0,
        sources=["news"],
        ch_v1=fake,
        insert_articles=lambda rows: len(rows),
        batch_size=2,
    )

    assert result["articles_inserted"] == 2
    assert "LIMIT 2 OFFSET 0" in fake.queries[0]
    assert "LIMIT 2 OFFSET 2" in fake.queries[1]
