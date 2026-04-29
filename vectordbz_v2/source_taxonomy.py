"""Source taxonomy and low-noise signal digest helpers for VectorDBZ V2."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


SOURCE_ORDER = [
    "job_market",
    "paper_top_venue",
    "github_repo",
    "hf_model",
    "hf_dataset",
    "hf_space",
    "reddit_subtrend",
    "news",
]

TOP_VENUES_A_STAR = {
    "neurips",
    "nips",
    "icml",
    "iclr",
    "cvpr",
    "acl",
    "kdd",
    "sigmod",
    "vldb",
    "sosp",
    "osdi",
    "pldi",
}

TOP_VENUES_A = {
    "emnlp",
    "naacl",
    "aaai",
    "ijcai",
    "eccv",
    "iccv",
    "sigir",
    "www",
    "chi",
    "uist",
    "icra",
    "iros",
    "rss",
}


@dataclass(frozen=True)
class SourceSignal:
    """A compact, display-ready signal after source-specific scoring."""

    category: str
    source_type: str
    source_id: str
    title: str
    score: float
    source_url: str = ""
    tier: str = ""
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "title": self.title,
            "score": round(self.score, 3),
            "source_url": self.source_url,
            "tier": self.tier,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


def parse_metadata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def paper_tier(metadata: dict[str, Any]) -> str:
    rank = str(
        metadata.get("venue_rank")
        or metadata.get("conference_rank")
        or metadata.get("ccf_rank")
        or ""
    ).upper()
    if rank in {"A*", "A"}:
        return rank

    venue = str(
        metadata.get("venue")
        or metadata.get("conference")
        or metadata.get("journal")
        or ""
    ).lower()
    tokens = {
        token.strip(" .:-_/()[]{}")
        for token in venue.replace("-", " ").replace("_", " ").split()
    }
    if tokens & TOP_VENUES_A_STAR:
        return "A*"
    if tokens & TOP_VENUES_A:
        return "A"
    return "preprint"


def canonical_category(article: dict[str, Any]) -> str:
    metadata = parse_metadata(article.get("metadata"))
    source_type = str(article.get("source_type") or "").lower()
    nested_source = str(metadata.get("source") or "").lower()

    if source_type in {"github", "github_repo"} or nested_source == "github":
        return "github_repo"

    if source_type in {"hf_model", "hf_dataset", "hf_space"}:
        return source_type
    if source_type == "hf_trending" or nested_source == "hf_trending":
        category = str(metadata.get("category") or metadata.get("repo_type") or "").lower()
        if category in {"model", "models"}:
            return "hf_model"
        if category in {"dataset", "datasets"}:
            return "hf_dataset"
        if category in {"space", "spaces"}:
            return "hf_space"
        return "hf_model"

    if source_type in {"reddit", "reddit_local"}:
        return "reddit_subtrend"

    if source_type == "paper":
        return "paper_top_venue" if paper_tier(metadata) in {"A*", "A"} else "paper_candidate"

    if source_type in {"job", "jobs", "job_market"}:
        return "job_market"

    return source_type or "news"


def _num(metadata: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = metadata.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _recency_bonus(article: dict[str, Any], now: datetime | None) -> float:
    if now is None:
        return 0.0
    value = article.get("collected_at") or article.get("published_at")
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
    if not isinstance(value, datetime):
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    age_days = max((now - value).total_seconds() / 86400, 0)
    return max(12.0 - age_days * 2.0, 0.0)


def score_article(article: dict[str, Any], now: datetime | None = None) -> float:
    metadata = parse_metadata(article.get("metadata"))
    category = canonical_category(article)
    score = _recency_bonus(article, now)

    if category == "github_repo":
        score += math.log1p(_num(metadata, "stars", "stargazers_count")) * 10
        score += math.log1p(_num(metadata, "forks", "forks_count")) * 2
        score += min(len(metadata.get("topics") or []), 8) * 1.5
    elif category in {"hf_model", "hf_dataset", "hf_space"}:
        score += math.log1p(_num(metadata, "likes")) * 12
        score += math.log1p(_num(metadata, "downloads")) * 8
        score += _num(metadata, "trendingScore", "trending_score") * 2
    elif category == "reddit_subtrend":
        score += math.log1p(_num(metadata, "score")) * 15
        score += math.log1p(_num(metadata, "num_comments", "comments")) * 6
        score += _num(metadata, "upvote_ratio") * 10
    elif category in {"paper_top_venue", "paper_candidate"}:
        tier = paper_tier(metadata)
        score += {"A*": 110.0, "A": 85.0}.get(tier, 30.0)
        score += math.log1p(_num(metadata, "citation_count", "citations")) * 6
        score += math.log1p(_num(metadata, "github_stars")) * 4
        score += math.log1p(_num(metadata, "hf_upvotes")) * 4
    elif category == "job_market":
        skills = str(metadata.get("skills") or article.get("content") or "")
        skill_hits = sum(
            token in skills.lower()
            for token in ["agent", "rag", "eval", "llm", "multimodal", "infra"]
        )
        score += 70.0 + skill_hits * 6.0
        if metadata.get("salary"):
            score += 15.0
        if metadata.get("company"):
            score += 5.0
    else:
        score += _num(metadata, "score")

    return score


def to_signal(article: dict[str, Any], now: datetime | None = None) -> SourceSignal | None:
    source_id = str(article.get("source_id") or "").strip()
    title = str(article.get("title") or "").strip()
    if not source_id or not title:
        return None

    metadata = parse_metadata(article.get("metadata"))
    category = canonical_category(article)
    tier = paper_tier(metadata) if category.startswith("paper_") else ""
    evidence = _evidence_for(category, metadata, tier)
    return SourceSignal(
        category=category,
        source_type=str(article.get("source_type") or ""),
        source_id=source_id,
        title=title,
        source_url=str(article.get("source_url") or article.get("url") or ""),
        score=score_article(article, now=now),
        tier=tier,
        evidence=evidence,
        metadata=metadata,
    )


def _evidence_for(category: str, metadata: dict[str, Any], tier: str) -> list[str]:
    if category == "github_repo":
        return [
            f"stars={int(_num(metadata, 'stars', 'stargazers_count'))}",
            f"forks={int(_num(metadata, 'forks', 'forks_count'))}",
        ]
    if category.startswith("hf_"):
        return [
            f"likes={int(_num(metadata, 'likes'))}",
            f"downloads={int(_num(metadata, 'downloads'))}",
        ]
    if category == "reddit_subtrend":
        return [
            f"subreddit={metadata.get('subreddit', '')}",
            f"comments={int(_num(metadata, 'num_comments', 'comments'))}",
        ]
    if category.startswith("paper_"):
        return [f"tier={tier}", f"venue={metadata.get('venue') or metadata.get('conference') or ''}"]
    if category == "job_market":
        return [
            f"company={metadata.get('company', '')}",
            f"skills={metadata.get('skills', '')}",
        ]
    return []


def build_signal_digest(
    articles: list[dict[str, Any]],
    now: datetime | None = None,
    per_source_limit: int = 5,
    global_limit: int = 10,
) -> dict[str, Any]:
    signals = [signal for article in articles if (signal := to_signal(article, now=now))]
    buckets: dict[str, list[SourceSignal]] = {}
    for signal in signals:
        buckets.setdefault(signal.category, []).append(signal)

    top_by_source: dict[str, list[dict[str, Any]]] = {}
    for category in _ordered_categories(buckets):
        ranked = sorted(buckets[category], key=lambda item: item.score, reverse=True)
        top_by_source[category] = [item.as_dict() for item in ranked[:per_source_limit]]

    strongest = _interleave_top_signals(top_by_source, global_limit)
    return {
        "source_counts": {category: len(items) for category, items in buckets.items()},
        "top_by_source": top_by_source,
        "strongest_signals": strongest,
    }


def _ordered_categories(buckets: dict[str, list[SourceSignal]]) -> list[str]:
    known = [category for category in SOURCE_ORDER if category in buckets]
    unknown = sorted(category for category in buckets if category not in SOURCE_ORDER)
    return known + unknown


def _interleave_top_signals(
    top_by_source: dict[str, list[dict[str, Any]]],
    global_limit: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    categories = list(top_by_source)
    rank = 0
    while len(selected) < global_limit:
        added = False
        for category in categories:
            items = top_by_source[category]
            if rank < len(items):
                selected.append(items[rank])
                added = True
                if len(selected) >= global_limit:
                    break
        if not added:
            break
        rank += 1
    return selected
