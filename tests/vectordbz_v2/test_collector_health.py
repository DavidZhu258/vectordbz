from vectordbz_v2 import collector_health


def test_collector_health_dry_run_reports_each_v2_source(monkeypatch):
    monkeypatch.setattr(collector_health, "collect_github_repos", lambda query, limit: [{"source_type": "github_repo"}])
    monkeypatch.setattr(
        collector_health,
        "collect_hf_trending",
        lambda limit_per_type: [
            {"source_type": "hf_model"},
            {"source_type": "hf_dataset"},
            {"source_type": "hf_space"},
        ],
    )
    monkeypatch.setattr(collector_health, "collect_news_from_v1", lambda limit: [{"source_type": "news"}])
    monkeypatch.setattr(collector_health, "collect_reddit_from_v1", lambda limit, months: [{"source_type": "reddit"}])
    monkeypatch.setattr(collector_health, "collect_jobs_from_v1", lambda limit: [{"source_type": "job"}])
    monkeypatch.setattr(collector_health, "collect_papers_from_v1", lambda limit: [{"source_type": "paper"}])

    result = collector_health.run_collector_health_check(limit=1)

    assert result["state"] == "ok"
    assert result["missing_article_sources"] == []
    assert result["sources"]["github"]["fetched"] == 1
    assert result["sources"]["hf"]["fetched"] == 3
    assert result["sources"]["reddit"]["fetched"] == 1
    assert result["sources"]["jobs"]["fetched"] == 1
    assert result["sources"]["papers"]["fetched"] == 1


def test_collector_health_reports_missing_hf_subtypes(monkeypatch):
    monkeypatch.setattr(collector_health, "collect_github_repos", lambda query, limit: [{"source_type": "github_repo"}])
    monkeypatch.setattr(collector_health, "collect_hf_trending", lambda limit_per_type: [])
    monkeypatch.setattr(collector_health, "collect_news_from_v1", lambda limit: [{"source_type": "news"}])
    monkeypatch.setattr(collector_health, "collect_reddit_from_v1", lambda limit, months: [{"source_type": "reddit"}])
    monkeypatch.setattr(collector_health, "collect_jobs_from_v1", lambda limit: [{"source_type": "job"}])
    monkeypatch.setattr(collector_health, "collect_papers_from_v1", lambda limit: [{"source_type": "paper"}])

    result = collector_health.run_collector_health_check(limit=1)

    assert result["state"] == "degraded"
    assert result["missing_article_sources"] == ["hf_dataset", "hf_model", "hf_space"]


def test_collector_health_uses_seeded_v2_articles_when_v1_tables_are_absent(monkeypatch):
    missing = RuntimeError("DB::Exception: Unknown table expression identifier 'papers'. (UNKNOWN_TABLE)")

    monkeypatch.setattr(collector_health, "collect_github_repos", lambda query, limit: [{"source_type": "github_repo"}])
    monkeypatch.setattr(
        collector_health,
        "collect_hf_trending",
        lambda limit_per_type: [
            {"source_type": "hf_model"},
            {"source_type": "hf_dataset"},
            {"source_type": "hf_space"},
        ],
    )
    monkeypatch.setattr(collector_health, "collect_news_from_v1", lambda limit: (_ for _ in ()).throw(missing))
    monkeypatch.setattr(collector_health, "collect_reddit_from_v1", lambda limit, months: (_ for _ in ()).throw(missing))
    monkeypatch.setattr(collector_health, "collect_jobs_from_v1", lambda limit: (_ for _ in ()).throw(missing))
    monkeypatch.setattr(collector_health, "collect_papers_from_v1", lambda limit: (_ for _ in ()).throw(missing))
    monkeypatch.setattr(
        collector_health,
        "collect_recent_articles_from_v2",
        lambda source_type, limit: [{"source_type": source_type, "source_id": f"{source_type}-1"}],
    )

    result = collector_health.run_collector_health_check(limit=1)

    assert result["state"] == "ok"
    assert result["failed_collectors"] == []
    assert result["sources"]["papers"]["fallback"] == "analytics_v2"
