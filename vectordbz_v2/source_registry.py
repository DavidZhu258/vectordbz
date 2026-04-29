"""Small source registry and quality rules for V2 collectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .source_taxonomy import parse_metadata


DEFAULT_REDDIT_SUBREDDITS = [
    "LocalLLaMA",
    "AI_Agents",
    "MachineLearning",
    "LLMDevs",
    "artificial",
    "SaaS",
    "startups",
    "ProductManagement",
    "datascience",
    "datasets",
    "MLQuestions",
]

PROMOTIONAL_TERMS = (
    "giveaway",
    "buy now",
    "free credits",
    "promo",
    "promotion",
    "newsletter",
    "limited time",
    "subscribe",
)


@dataclass(frozen=True)
class SourceRule:
    name: str
    source_type: str
    category: str
    purpose: str
    min_score: int = 0
    min_comments: int = 0
    freshness_hours: int = 72
    critical: bool = False
    exclude_terms: tuple[str, ...] = field(default_factory=lambda: PROMOTIONAL_TERMS)


def default_source_registry() -> dict[str, SourceRule]:
    """Return the curated default source registry."""
    return {
        "LocalLLaMA": SourceRule(
            name="LocalLLaMA",
            source_type="reddit",
            category="ai_agent",
            purpose="local LLM deployment, cost, model, and agent operations",
            min_score=100,
            min_comments=20,
        ),
        "AI_Agents": SourceRule(
            name="AI_Agents",
            source_type="reddit",
            category="ai_agent",
            purpose="agent orchestration, production workflows, and safety failures",
            min_score=30,
            min_comments=5,
        ),
        "MachineLearning": SourceRule(
            name="MachineLearning",
            source_type="reddit",
            category="research",
            purpose="paper discussion, reproducibility, and applied research judgment",
            min_score=50,
            min_comments=10,
        ),
        "LLMDevs": SourceRule(
            name="LLMDevs",
            source_type="reddit",
            category="ai_agent",
            purpose="developer implementation details for LLM applications",
            min_score=20,
            min_comments=3,
        ),
        "artificial": SourceRule(
            name="artificial",
            source_type="reddit",
            category="ai_news",
            purpose="broad AI industry discussion filtered for confirmed signals",
            min_score=80,
            min_comments=15,
        ),
        "SaaS": SourceRule(
            name="SaaS",
            source_type="reddit",
            category="product_market",
            purpose="pricing, product pain, workflow adoption, and buyer objections",
            min_score=25,
            min_comments=5,
        ),
        "startups": SourceRule(
            name="startups",
            source_type="reddit",
            category="product_market",
            purpose="market validation, distribution pain, and founder failure cases",
            min_score=30,
            min_comments=5,
        ),
        "ProductManagement": SourceRule(
            name="ProductManagement",
            source_type="reddit",
            category="product_market",
            purpose="workflow, UX, and prioritization discussions",
            min_score=20,
            min_comments=5,
        ),
        "datascience": SourceRule(
            name="datascience",
            source_type="reddit",
            category="data_practice",
            purpose="data workflow, analytics, and production reliability pain",
            min_score=35,
            min_comments=5,
        ),
        "datasets": SourceRule(
            name="datasets",
            source_type="reddit",
            category="data_practice",
            purpose="new datasets and data-access bottlenecks",
            min_score=15,
            min_comments=2,
        ),
        "MLQuestions": SourceRule(
            name="MLQuestions",
            source_type="reddit",
            category="data_practice",
            purpose="practical ML implementation blockers and recurring questions",
            min_score=10,
            min_comments=2,
        ),
    }


def evaluate_reddit_candidate(article: dict[str, Any]) -> dict[str, Any]:
    """Evaluate whether a Reddit article is worth surfacing."""
    metadata = parse_metadata(article.get("metadata"))
    subreddit = str(metadata.get("subreddit") or "").strip()
    registry = default_source_registry()
    rule = registry.get(subreddit)
    if rule is None:
        return {
            "accepted": False,
            "source_rule": "",
            "category": "",
            "reason": f"subreddit {subreddit or '<missing>'} is not in the curated registry",
        }

    text = f"{article.get('title', '')}\n{article.get('content', '')}".lower()
    if any(term in text for term in rule.exclude_terms):
        return {
            "accepted": False,
            "source_rule": rule.name,
            "category": rule.category,
            "reason": "excluded promotional or low-signal wording",
        }

    score = _to_int(metadata.get("score"))
    comments = _to_int(metadata.get("num_comments") or metadata.get("comments"))
    accepted = score >= rule.min_score and comments >= rule.min_comments
    reason = (
        f"meets {rule.name} thresholds: score>={rule.min_score}, "
        f"comments>={rule.min_comments}"
    )
    if not accepted:
        reason = (
            f"below {rule.name} thresholds: score={score}/{rule.min_score}, "
            f"comments={comments}/{rule.min_comments}"
        )

    return {
        "accepted": accepted,
        "source_rule": rule.name,
        "category": rule.category,
        "reason": reason,
        "thresholds": {
            "min_score": rule.min_score,
            "min_comments": rule.min_comments,
            "freshness_hours": rule.freshness_hours,
        },
        "purpose": rule.purpose,
    }


def annotate_article_with_source_rule(article: dict[str, Any]) -> dict[str, Any]:
    """Attach registry selection metadata without mutating the input article."""
    annotated = dict(article)
    metadata = dict(parse_metadata(article.get("metadata")))
    if str(article.get("source_type") or "").lower() == "reddit":
        verdict = evaluate_reddit_candidate(article)
        metadata["source_rule"] = verdict.get("source_rule", "")
        metadata["source_rule_category"] = verdict.get("category", "")
        metadata["selection_reason"] = verdict.get("reason", "")
        metadata["selection_accepted"] = bool(verdict.get("accepted"))
        if verdict.get("thresholds"):
            metadata["selection_thresholds"] = verdict["thresholds"]
    annotated["metadata"] = metadata
    return annotated


def _to_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0
