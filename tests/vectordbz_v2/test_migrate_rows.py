from datetime import date, datetime

from vectordbz_v2.migrate import (
    _job_row_to_article,
    _migration_page_size,
    _news_row_to_article,
    _paper_row_to_article,
    _reddit_row_to_article,
)


def test_job_row_to_article_converts_date_fields_to_datetimes():
    article = _job_row_to_article(
        (
            "job-1",
            "AI Agent Engineer",
            "Acme AI",
            "Remote",
            "$180k",
            "Build agentic RAG systems",
            "https://example.com/job",
            "jobspy",
            date(2026, 4, 28),
            date(2026, 4, 28),
            "agents, rag",
        )
    )

    assert article["source_type"] == "job"
    assert isinstance(article["published_at"], datetime)
    assert isinstance(article["collected_at"], datetime)


def test_paper_row_to_article_rejects_missing_source_id():
    article = _paper_row_to_article(
        (
            "",
            "Useful paper without id",
            "Abstract",
            "A. Researcher",
            "cs.AI",
            "cs.AI",
            "",
            date(2026, 4, 28),
            datetime(2026, 4, 28),
            0,
            0,
            0,
        )
    )

    assert article is None


def test_reddit_row_to_article_uses_body_fallback_when_title_is_empty():
    article = _reddit_row_to_article(
        (
            "abc123",
            "",
            "People are asking how to deploy local agent workflows reliably.",
            "https://reddit.com/comments/abc123",
            "LocalLLaMA",
            "user",
            500,
            80,
            0.94,
            datetime(2026, 4, 28),
            datetime(2026, 4, 28),
        )
    )

    assert article is not None
    assert article["title"].startswith("[r/LocalLLaMA]")
    assert "deploy local agent" in article["title"]


def test_migration_page_size_batches_full_migrations():
    assert _migration_page_size(limit=0, total=0, batch_size=5000) == 5000
    assert _migration_page_size(limit=6500, total=5000, batch_size=5000) == 1500
    assert _migration_page_size(limit=6500, total=6500, batch_size=5000) == 0


def test_news_row_to_article_keeps_github_and_hf_source_aware():
    github_article = _news_row_to_article(
        (
            "gh-1",
            "owner/repo",
            "GitHub repo launch",
            "https://github.com/owner/repo",
            "github",
            datetime(2026, 4, 28),
            datetime(2026, 4, 28),
            ["agents"],
            '{"stars": 1200}',
        )
    )
    hf_article = _news_row_to_article(
        (
            "hf-1",
            "org/model",
            "HF model trending",
            "https://huggingface.co/org/model",
            "hf_trending",
            datetime(2026, 4, 28),
            datetime(2026, 4, 28),
            ["llm"],
            '{"category": "models", "likes": 99}',
        )
    )

    assert github_article["source_type"] == "github_repo"
    assert github_article["metadata"]["source"] == "github"
    assert github_article["metadata"]["stars"] == 1200
    assert hf_article["source_type"] == "hf_model"
    assert hf_article["metadata"]["source"] == "hf_trending"
