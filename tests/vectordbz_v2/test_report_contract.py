from datetime import datetime, timezone

from vectordbz_v2.report_contract import build_report_contract
from vectordbz_v2.source_taxonomy import build_signal_digest


NOW = datetime(2026, 4, 28, tzinfo=timezone.utc)


def test_report_contract_curates_top_venue_papers_before_preprints():
    articles = [
        {
            "source_type": "paper",
            "source_id": "astar-1",
            "title": "Reliable Agent Evaluation",
            "metadata": {"venue": "NeurIPS", "venue_rank": "A*", "citation_count": 12},
            "collected_at": NOW,
        },
        {
            "source_type": "paper",
            "source_id": "a-1",
            "title": "Efficient Multimodal Retrieval",
            "metadata": {"conference": "EMNLP", "venue_rank": "A", "citation_count": 8},
            "collected_at": NOW,
        },
        {
            "source_type": "paper",
            "source_id": "preprint-1",
            "title": "High-Signal Agent Preprint",
            "metadata": {"primary_category": "cs.AI", "github_stars": 5_000, "hf_upvotes": 600},
            "collected_at": NOW,
        },
        {
            "source_type": "paper",
            "source_id": "preprint-2",
            "title": "Low-Signal Preprint",
            "metadata": {"primary_category": "cs.CL"},
            "collected_at": NOW,
        },
    ]
    digest = build_signal_digest(articles, now=NOW, per_source_limit=10, global_limit=10)

    report = build_report_contract(digest, source_health={"state": "ok"})

    assert [item["source_id"] for item in report["best_papers"]["top_venue"]] == [
        "astar-1",
        "a-1",
    ]
    assert [item["source_id"] for item in report["best_papers"]["preprints"]] == ["preprint-1"]
    assert "preprint-2" not in {
        item["source_id"]
        for group in report["best_papers"].values()
        for item in group
    }


def test_report_contract_groups_job_opportunity_directions_by_skill_signal():
    articles = [
        {
            "source_type": "job",
            "source_id": "job-1",
            "title": "AI Agent Engineer",
            "metadata": {
                "company": "Acme AI",
                "salary": "$180k",
                "skills": "agents, rag, evals",
            },
            "collected_at": NOW,
        },
        {
            "source_type": "job",
            "source_id": "job-2",
            "title": "RAG Platform Engineer",
            "metadata": {
                "company": "SearchWorks",
                "skills": "retrieval, rag, vector databases",
            },
            "collected_at": NOW,
        },
        {
            "source_type": "job",
            "source_id": "job-3",
            "title": "Multimodal Applied Scientist",
            "metadata": {
                "company": "VisionLab",
                "skills": "multimodal, evals",
            },
            "collected_at": NOW,
        },
    ]
    digest = build_signal_digest(articles, now=NOW, per_source_limit=5, global_limit=10)

    report = build_report_contract(digest, source_health={"state": "ok"})

    directions = report["job_opportunity_directions"]
    assert directions[0]["direction"] == "rag"
    assert directions[0]["recent_openings"] == 2
    assert directions[0]["market_signal"] == "positive"
    assert {job["source_id"] for job in directions[0]["top_jobs"]} == {"job-1", "job-2"}


def test_report_contract_records_no_jobs_as_negative_market_signal():
    digest = build_signal_digest([], now=NOW, per_source_limit=5, global_limit=10)

    report = build_report_contract(
        digest,
        source_health={"state": "ok", "warnings": ["job_market:no_recent_jobs"]},
    )

    assert report["job_opportunity_directions"] == [
        {
            "direction": "overall_market",
            "recent_openings": 0,
            "market_signal": "negative",
            "reason": "No recent job openings passed the market-signal filters.",
            "top_jobs": [],
        }
    ]


def test_report_contract_recovers_job_direction_from_source_url_slug():
    articles = [
        {
            "source_type": "job",
            "source_id": "job-cloud-1",
            "title": "Europe",
            "source_url": "https://startup.jobs/staff-cloud-engineer-zoox-7884030",
            "metadata": {"company": "Anduril Industries", "skills": ""},
            "collected_at": NOW,
        }
    ]
    digest = build_signal_digest(articles, now=NOW, per_source_limit=5, global_limit=10)

    report = build_report_contract(digest, source_health={"state": "ok"})

    assert report["job_opportunity_directions"][0]["direction"] == "infra"


def test_report_contract_includes_evidence_signals_for_ui_and_qa():
    articles = [
        {
            "source_type": "reddit",
            "source_id": "rd-evidence-1",
            "title": "Agent tools need failure recovery",
            "source_url": "https://reddit.com/r/AI_Agents/comments/rd-evidence-1",
            "metadata": {
                "subreddit": "AI_Agents",
                "score": 80,
                "num_comments": 12,
                "selection_reason": "meets AI_Agents thresholds: score>=30, comments>=5",
            },
            "collected_at": NOW,
        }
    ]
    digest = build_signal_digest(articles, now=NOW, per_source_limit=5, global_limit=10)

    report = build_report_contract(digest, source_health={"state": "ok"})

    assert report["evidence_signals"][0]["claim"] == "Agent tools need failure recovery"
    assert report["evidence_signals"][0]["confidence"] != "low"
    assert report["evidence_signals"][0]["evidence_spans"][0]["evidence_id"] == (
        "reddit:rd-evidence-1:1"
    )
