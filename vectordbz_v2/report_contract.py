"""Deterministic daily/weekly report contract builders."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .evidence_contract import build_evidence_signal


PREPRINT_MIN_SCORE = 60.0
PAPER_TIER_ORDER = {"A*": 0, "A": 1, "preprint": 2, "": 3}
JOB_DIRECTION_RULES = [
    ("rag", ("rag", "retrieval", "vector database", "vector databases")),
    ("agents", ("agent", "agents", "agentic")),
    ("evals", ("eval", "evals", "evaluation", "benchmark")),
    ("multimodal", ("multimodal", "vision language", "vlm")),
    ("llm", ("llm", "language model", "large language model")),
    ("infra", ("infra", "platform", "deployment", "serving", "cloud", "engineer")),
]


def build_report_contract(
    digest: dict[str, Any],
    source_health: dict[str, Any] | None = None,
    top_venue_limit: int = 5,
    preprint_limit: int = 3,
    job_direction_limit: int = 5,
) -> dict[str, Any]:
    """Build the deterministic report payload before any LLM narration."""
    source_health = source_health or {"state": "unknown"}
    top_by_source = digest.get("top_by_source", {})

    return {
        "source_counts": digest.get("source_counts", {}),
        "source_health": source_health,
        "top_by_source": top_by_source,
        "strongest_signals": digest.get("strongest_signals", []),
        "evidence_signals": [
            build_evidence_signal(signal)
            for signal in digest.get("strongest_signals", [])
        ],
        "best_papers": _best_papers(top_by_source, top_venue_limit, preprint_limit),
        "job_opportunity_directions": _job_directions(
            top_by_source.get("job_market", []),
            source_health,
            job_direction_limit,
        ),
    }


def _best_papers(
    top_by_source: dict[str, list[dict[str, Any]]],
    top_venue_limit: int,
    preprint_limit: int,
) -> dict[str, list[dict[str, Any]]]:
    top_venue = list(top_by_source.get("paper_top_venue", []))
    preprints = list(top_by_source.get("paper_candidate", []))

    top_venue.sort(key=lambda item: (_paper_tier_rank(item), -float(item.get("score", 0))))
    curated_preprints = [
        item
        for item in sorted(preprints, key=lambda item: float(item.get("score", 0)), reverse=True)
        if float(item.get("score", 0)) >= PREPRINT_MIN_SCORE
    ]

    return {
        "top_venue": top_venue[:top_venue_limit],
        "preprints": curated_preprints[:preprint_limit],
    }


def _paper_tier_rank(item: dict[str, Any]) -> int:
    return PAPER_TIER_ORDER.get(str(item.get("tier") or ""), 9)


def _job_directions(
    job_signals: list[dict[str, Any]],
    source_health: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    warnings = set(source_health.get("warnings", []))
    if not job_signals and "job_market:no_recent_jobs" in warnings:
        return [
            {
                "direction": "overall_market",
                "recent_openings": 0,
                "market_signal": "negative",
                "reason": "No recent job openings passed the market-signal filters.",
                "top_jobs": [],
            }
        ]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for job in job_signals:
        directions = _directions_for_job(job)
        for direction in directions:
            grouped[direction].append(job)

    ranked = []
    for direction, jobs in grouped.items():
        top_jobs = sorted(jobs, key=lambda item: float(item.get("score", 0)), reverse=True)
        ranked.append(
            {
                "direction": direction,
                "recent_openings": len(jobs),
                "market_signal": "positive",
                "reason": _direction_reason(direction, len(jobs)),
                "top_jobs": top_jobs[:3],
            }
        )

    ranked.sort(key=lambda item: (-item["recent_openings"], _direction_priority(item["direction"])))
    return ranked[:limit]


def _directions_for_job(job: dict[str, Any]) -> list[str]:
    metadata = job.get("metadata") or {}
    haystack = " ".join(
        str(value)
        for value in [
            job.get("title", ""),
            job.get("source_url", ""),
            job.get("content", ""),
            metadata.get("skills", ""),
            metadata.get("company", ""),
        ]
    ).lower()

    directions = [
        direction
        for direction, aliases in JOB_DIRECTION_RULES
        if any(_contains_term(haystack, alias) for alias in aliases)
    ]
    return directions or ["general_ai"]


def _contains_term(haystack: str, term: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def _direction_priority(direction: str) -> int:
    for idx, (candidate, _) in enumerate(JOB_DIRECTION_RULES):
        if direction == candidate:
            return idx
    return len(JOB_DIRECTION_RULES)


def _direction_reason(direction: str, openings: int) -> str:
    if openings == 1:
        return f"One recent job opening explicitly matched {direction} skills."
    return f"{openings} recent job openings explicitly matched {direction} skills."
