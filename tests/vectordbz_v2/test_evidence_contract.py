from datetime import datetime, timezone

from vectordbz_v2.evidence_contract import (
    build_cited_answer_payload,
    build_evidence_signal,
)


NOW = datetime(2026, 4, 28, tzinfo=timezone.utc)


def test_build_evidence_signal_extracts_citable_spans_and_confidence():
    signal = build_evidence_signal(
        {
            "source_type": "reddit",
            "source_id": "rd-1",
            "title": "Long-running agents lose state",
            "source_url": "https://reddit.com/r/LocalLLaMA/comments/rd-1",
            "score": 0.91,
            "metadata": {
                "subreddit": "LocalLLaMA",
                "selection_reason": "meets LocalLLaMA thresholds: score>=100, comments>=20",
            },
            "evidence": [
                "Users report losing an hour of work after context overflow.",
                "State persistence is the proposed fix.",
            ],
        },
        now=NOW,
    )

    assert signal["claim"] == "Long-running agents lose state"
    assert signal["confidence"] == "high"
    assert signal["evidence_spans"][0]["evidence_id"] == "reddit:rd-1:1"
    assert signal["evidence_spans"][0]["source_url"].startswith("https://reddit.com/")
    assert signal["why_now"] == "meets LocalLLaMA thresholds: score>=100, comments>=20"


def test_build_evidence_signal_marks_missing_or_stale_evidence_as_low_confidence():
    signal = build_evidence_signal(
        {
            "source_type": "news",
            "source_id": "old-1",
            "title": "Old AI launch",
            "source_url": "https://example.com/old",
            "metadata": {"collected_at": "2025-12-01T00:00:00+00:00"},
            "evidence": [],
        },
        now=NOW,
        stale_days=30,
    )

    assert signal["confidence"] == "low"
    assert "no evidence spans" in signal["counter_evidence"]
    assert "stale" in signal["counter_evidence"]


def test_cited_answer_payload_uses_only_evidence_backed_signals():
    payload = build_cited_answer_payload(
        query="Why should we avoid heavy agent frameworks?",
        signals=[
            {
                "source_type": "reddit",
                "source_id": "rd-1",
                "title": "Heavy frameworks add latency",
                "source_url": "https://reddit.com/r/LocalLLaMA/comments/rd-1",
                "metadata": {"selection_reason": "meets LocalLLaMA thresholds: score>=100, comments>=20"},
                "evidence": ["Tool call latency and failure recovery matter more than model choice."],
            },
            {
                "source_type": "news",
                "source_id": "thin-1",
                "title": "Thin unsupported claim",
                "source_url": "https://example.com/thin",
                "evidence": [],
            },
        ],
        now=NOW,
    )

    assert payload["answer_state"] == "answerable"
    assert "Heavy frameworks add latency" in payload["answer"]
    assert payload["citations"] == ["reddit:rd-1:1"]
    assert payload["signals_used"] == ["rd-1"]
    assert payload["signals_skipped"] == ["thin-1"]
