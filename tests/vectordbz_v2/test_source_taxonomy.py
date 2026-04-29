from datetime import datetime, timezone

from vectordbz_v2.source_taxonomy import (
    build_signal_digest,
    canonical_category,
    paper_tier,
)


NOW = datetime(2026, 4, 28, tzinfo=timezone.utc)


def test_canonical_category_keeps_hf_github_reddit_paper_and_job_separate():
    articles = [
        {
            "source_type": "news",
            "source_id": "gh-1",
            "title": "fast-agent",
            "metadata": {"source": "github", "full_name": "acme/fast-agent"},
        },
        {
            "source_type": "news",
            "source_id": "hf-1",
            "title": "org/model",
            "metadata": {"source": "hf_trending", "category": "models"},
        },
        {
            "source_type": "reddit",
            "source_id": "rd-1",
            "title": "Agent framework adoption thread",
            "metadata": {"subreddit": "LocalLLaMA"},
        },
        {
            "source_type": "paper",
            "source_id": "paper-1",
            "title": "A top conference paper",
            "metadata": {"venue": "NeurIPS", "venue_rank": "A*"},
        },
        {
            "source_type": "job",
            "source_id": "job-1",
            "title": "Founding AI Engineer",
            "metadata": {"company": "Acme AI", "skills": "agents, rag"},
        },
    ]

    assert [canonical_category(a) for a in articles] == [
        "github_repo",
        "hf_model",
        "reddit_subtrend",
        "paper_top_venue",
        "job_market",
    ]


def test_paper_tier_detects_top_venues_and_rank_metadata():
    assert paper_tier({"venue": "NeurIPS"}) == "A*"
    assert paper_tier({"conference": "EMNLP"}) == "A"
    assert paper_tier({"venue_rank": "A"}) == "A"
    assert paper_tier({"primary_category": "cs.AI"}) == "preprint"


def test_signal_digest_caps_noise_but_preserves_each_source_top_signals():
    noisy_github = [
        {
            "source_type": "news",
            "source_id": f"gh-{i}",
            "title": f"repo-{i}",
            "source_url": f"https://github.com/acme/repo-{i}",
            "metadata": {
                "source": "github",
                "full_name": f"acme/repo-{i}",
                "stars": 10_000 - i,
                "forks": 500,
                "topics": ["agents"],
            },
            "collected_at": NOW,
        }
        for i in range(30)
    ]
    other_sources = [
        {
            "source_type": "news",
            "source_id": "hf-model-1",
            "title": "org/agent-model",
            "metadata": {
                "source": "hf_trending",
                "category": "models",
                "likes": 300,
                "downloads": 20_000,
            },
            "collected_at": NOW,
        },
        {
            "source_type": "reddit",
            "source_id": "reddit-1",
            "title": "What agent tools are people paying for?",
            "metadata": {"subreddit": "LocalLLaMA", "score": 800, "num_comments": 160},
            "collected_at": NOW,
        },
        {
            "source_type": "paper",
            "source_id": "paper-1",
            "title": "Reliable Tool Use for Agents",
            "metadata": {"venue": "ICLR", "venue_rank": "A*"},
            "collected_at": NOW,
        },
        {
            "source_type": "job",
            "source_id": "job-1",
            "title": "AI Agent Engineer",
            "metadata": {
                "company": "Applied Agents",
                "salary": "$180k",
                "skills": "agent frameworks, rag, evals",
            },
            "collected_at": NOW,
        },
    ]

    digest = build_signal_digest(
        noisy_github + other_sources,
        now=NOW,
        per_source_limit=5,
        global_limit=10,
    )

    assert len(digest["top_by_source"]["github_repo"]) == 5
    assert set(digest["top_by_source"]) >= {
        "github_repo",
        "hf_model",
        "reddit_subtrend",
        "paper_top_venue",
        "job_market",
    }
    assert any(item["category"] == "job_market" for item in digest["strongest_signals"])
    assert len(digest["strongest_signals"]) <= 10
