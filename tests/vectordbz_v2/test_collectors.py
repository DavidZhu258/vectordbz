from datetime import datetime, timezone

import requests

from vectordbz_v2 import collectors


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_collect_github_repos_maps_search_results_to_source_aware_articles(monkeypatch):
    def fake_get(url, **kwargs):
        assert "api.github.com/search/repositories" in url
        assert kwargs["proxies"] == {"http": "", "https": ""}
        return _Response(
            {
                "items": [
                    {
                        "full_name": "owner/repo",
                        "name": "repo",
                        "description": "Agent framework",
                        "html_url": "https://github.com/owner/repo",
                        "stargazers_count": 1234,
                        "forks_count": 56,
                        "topics": ["agents", "rag"],
                        "updated_at": "2026-04-28T00:00:00Z",
                    }
                ]
            }
        )

    monkeypatch.setattr(collectors.requests, "get", fake_get)

    rows = collectors.collect_github_repos(query="agent framework", limit=1)

    assert rows[0]["source_type"] == "github_repo"
    assert rows[0]["source_id"] == "owner/repo"
    assert rows[0]["metadata"]["stars"] == 1234
    assert rows[0]["metadata"]["topics"] == ["agents", "rag"]


def test_collect_hf_trending_maps_models_datasets_and_spaces(monkeypatch):
    payloads = {
        "models": [{"id": "org/model", "likes": 10, "downloads": 100, "tags": ["text-generation"]}],
        "datasets": [{"id": "org/data", "likes": 5, "downloads": 20, "tags": ["benchmark"]}],
        "spaces": [{"id": "org/space", "likes": 3, "sdk": "gradio", "tags": ["demo"]}],
    }

    def fake_get(url, **kwargs):
        for key, payload in payloads.items():
            if f"/api/{key}" in url:
                assert kwargs["params"]["sort"] == "likes7d"
                assert kwargs["params"]["direction"] == "-1"
                assert kwargs["proxies"] == {"http": "", "https": ""}
                return _Response(payload)
        raise AssertionError(url)

    monkeypatch.setattr(collectors.requests, "get", fake_get)

    rows = collectors.collect_hf_trending(limit_per_type=1)

    assert [row["source_type"] for row in rows] == ["hf_model", "hf_dataset", "hf_space"]
    assert [row["source_id"] for row in rows] == ["org/model", "org/data", "org/space"]


def test_collect_hf_trending_falls_back_to_local_proxy_after_ssl_error(monkeypatch):
    calls = []
    proxy = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}

    def fake_get(url, **kwargs):
        calls.append(kwargs.get("proxies"))
        if len(calls) == 1:
            raise requests.exceptions.SSLError("eof")
        return _Response([{"id": "org/model", "likes": 10, "downloads": 100}])

    monkeypatch.setattr(collectors, "_detect_local_proxy", lambda: proxy)
    monkeypatch.setattr(collectors.requests, "get", fake_get)

    rows = collectors._hf_rows("models", "hf_model", 1)

    assert rows[0]["source_id"] == "org/model"
    assert calls == [collectors.NO_PROXY, proxy]


def test_run_source_collectors_inserts_rows_and_returns_health(monkeypatch):
    monkeypatch.setattr(collectors, "collect_github_repos", lambda query, limit: [{"source_type": "github_repo"}])
    monkeypatch.setattr(collectors, "collect_hf_trending", lambda limit_per_type: [{"source_type": "hf_model"}])
    monkeypatch.setattr(collectors, "collect_news_from_v1", lambda limit: [])
    monkeypatch.setattr(collectors, "collect_reddit_from_v1", lambda limit, months: [])
    monkeypatch.setattr(collectors, "collect_jobs_from_v1", lambda limit: [])
    monkeypatch.setattr(collectors, "collect_papers_from_v1", lambda limit: [])
    inserted = []
    monkeypatch.setattr(collectors, "ch_insert_articles", lambda rows: inserted.extend(rows) or len(rows))

    result = collectors.run_source_collectors(github_limit=1, hf_limit_per_type=1)

    assert result.fetch_ok is True
    assert result.source == "source_collectors"
    assert result.fetched == 2
    assert result.accepted == 2
    assert len(inserted) == 2


def test_run_source_collectors_preserves_partial_success(monkeypatch):
    monkeypatch.setattr(collectors, "collect_github_repos", lambda query, limit: (_ for _ in ()).throw(RuntimeError("github down")))
    monkeypatch.setattr(collectors, "collect_hf_trending", lambda limit_per_type: [{"source_type": "hf_model"}])
    monkeypatch.setattr(collectors, "collect_news_from_v1", lambda limit: [])
    monkeypatch.setattr(collectors, "collect_reddit_from_v1", lambda limit, months: [])
    monkeypatch.setattr(collectors, "collect_jobs_from_v1", lambda limit: [])
    monkeypatch.setattr(collectors, "collect_papers_from_v1", lambda limit: [])
    inserted = []
    monkeypatch.setattr(collectors, "ch_insert_articles", lambda rows: inserted.extend(rows) or len(rows))

    result = collectors.run_source_collectors(github_limit=1, hf_limit_per_type=1)

    assert result.fetch_ok is False
    assert result.fetched == 1
    assert result.accepted == 1
    assert "github down" in result.error
    assert inserted == [{"source_type": "hf_model"}]


def test_run_source_collectors_treats_missing_v1_tables_as_optional_when_live_sources_succeed(monkeypatch):
    missing = RuntimeError("DB::Exception: Unknown table expression identifier 'papers'. (UNKNOWN_TABLE)")

    monkeypatch.setattr(collectors, "collect_github_repos", lambda query, limit: [{"source_type": "github_repo"}])
    monkeypatch.setattr(collectors, "collect_hf_trending", lambda limit_per_type: [{"source_type": "hf_model"}])
    monkeypatch.setattr(collectors, "collect_news_from_v1", lambda limit: (_ for _ in ()).throw(missing))
    monkeypatch.setattr(collectors, "collect_reddit_from_v1", lambda limit, months: (_ for _ in ()).throw(missing))
    monkeypatch.setattr(collectors, "collect_jobs_from_v1", lambda limit: (_ for _ in ()).throw(missing))
    monkeypatch.setattr(collectors, "collect_papers_from_v1", lambda limit: (_ for _ in ()).throw(missing))
    monkeypatch.setattr(collectors, "ch_insert_articles", lambda rows: len(rows))

    result = collectors.run_source_collectors(github_limit=1, hf_limit_per_type=1)

    assert result.fetch_ok is True
    assert result.fetched == 2
    assert "v1_source_missing" in result.error


def test_collect_reddit_subtrends_from_rows_adds_clear_sub_source_labels():
    rows = collectors.reddit_rows_to_articles(
        [
            {
                "event_id": "rd-1",
                "title": "Local agent deployment",
                "body": "People compare local agent deployment tools.",
                "url": "https://reddit.com/r/LocalLLaMA/comments/rd-1",
                "subreddit": "LocalLLaMA",
                "score": 500,
                "num_comments": 80,
                "upvote_ratio": 0.93,
            }
        ]
    )

    assert rows[0]["source_type"] == "reddit"
    assert rows[0]["metadata"]["sub_source"] == "reddit:LocalLLaMA"
    assert rows[0]["metadata"]["subreddit"] == "LocalLLaMA"
    assert rows[0]["metadata"]["source_rule"] == "LocalLLaMA"
    assert rows[0]["metadata"]["selection_accepted"] is True
    assert "score>=100" in rows[0]["metadata"]["selection_reason"]


def test_collect_news_from_v1_maps_rows_with_news_source(monkeypatch):
    class _Client:
        def query(self, sql):
            assert "FROM news" in sql
            return type("Result", (), {"result_rows": [
                (
                    "news-2",
                    "AI infra update",
                    "Body",
                    "https://example.com/news",
                    "rss",
                    datetime(2026, 4, 28, tzinfo=timezone.utc),
                    datetime(2026, 4, 28, tzinfo=timezone.utc),
                    ["ai"],
                    "{}",
                )
            ]})()

    monkeypatch.setattr(collectors, "get_ch_v1", lambda: _Client())

    rows = collectors.collect_news_from_v1(limit=1)

    assert rows[0]["source_type"] == "news"
    assert rows[0]["source_id"] == "news-2"


def test_reddit_rows_to_articles_accepts_clickhouse_datetime_values():
    published_at = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)

    rows = collectors.reddit_rows_to_articles(
        [
            {
                "event_id": "rd-2",
                "title": "Datetime payload",
                "created_at": published_at,
                "subreddit": "MachineLearning",
            }
        ]
    )

    assert rows[0]["published_at"] == published_at


def test_job_rows_to_articles_marks_jobs_as_critical_market_source():
    rows = collectors.job_rows_to_articles(
        [
            {
                "job_id": "job-1",
                "title": "RAG Platform Engineer",
                "company": "Acme",
                "source_url": "https://example.com/job-1",
                "skills": "rag, agents",
            }
        ]
    )

    assert rows[0]["source_type"] == "job"
    assert rows[0]["metadata"]["critical_source"] is True


def test_job_rows_to_articles_accepts_clickhouse_datetime_values():
    posted_date = datetime(2026, 4, 27, 9, 30, tzinfo=timezone.utc)

    rows = collectors.job_rows_to_articles(
        [
            {
                "job_id": "job-2",
                "title": "Data Platform Engineer",
                "posted_date": posted_date,
            }
        ]
    )

    assert rows[0]["published_at"] == posted_date


def test_enrich_paper_metadata_adds_venue_rank_from_known_venue():
    row = collectors.enrich_paper_row(
        {
            "source_type": "paper",
            "source_id": "paper-1",
            "title": "Reliable Agents at NeurIPS",
            "metadata": {"venue": "NeurIPS"},
        }
    )

    assert row["metadata"]["venue_rank"] == "A*"


def test_run_source_collectors_retries_transient_failures(monkeypatch):
    attempts = {"github": 0}

    def flaky_github(query, limit):
        attempts["github"] += 1
        if attempts["github"] == 1:
            raise RuntimeError("temporary")
        return [{"source_type": "github_repo"}]

    monkeypatch.setattr(collectors, "collect_github_repos", flaky_github)
    monkeypatch.setattr(collectors, "collect_hf_trending", lambda limit_per_type: [])
    monkeypatch.setattr(collectors, "collect_news_from_v1", lambda limit: [])
    monkeypatch.setattr(collectors, "collect_reddit_from_v1", lambda limit, months: [])
    monkeypatch.setattr(collectors, "collect_jobs_from_v1", lambda limit: [])
    monkeypatch.setattr(collectors, "collect_papers_from_v1", lambda limit: [])
    monkeypatch.setattr(collectors.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(collectors, "ch_insert_articles", lambda rows: len(rows))

    result = collectors.run_source_collectors(github_limit=1, hf_limit_per_type=1)

    assert attempts["github"] == 2
    assert result.fetch_ok is True
    assert result.attempts == 7
