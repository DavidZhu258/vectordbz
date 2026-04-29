"""Dry-run health check for V2 source collectors."""

from __future__ import annotations

import argparse
import json
import logging
from typing import Callable

from .collectors import (
    collect_github_repos,
    collect_hf_trending,
    collect_jobs_from_v1,
    collect_news_from_v1,
    collect_papers_from_v1,
    collect_recent_articles_from_v2,
    collect_reddit_from_v1,
    _is_missing_v1_source_error,
    _retry_call,
)
from .service_registry import validate_article_source_coverage

logger = logging.getLogger("vectordbz_v2.collector_health")


def _run_source(name: str, fn: Callable[[], list[dict]]) -> tuple[dict, set[str]]:
    try:
        rows, attempts = _retry_call(fn, attempts=2, base_delay_seconds=0.5)
        source_types = {str(row.get("source_type") or "") for row in rows if row.get("source_type")}
        return {
            "fetch_ok": True,
            "fetched": len(rows),
            "attempts": attempts,
            "source_types": sorted(source_types),
            "error": "",
        }, source_types
    except Exception as exc:
        return {
            "fetch_ok": False,
            "fetched": 0,
            "attempts": 2,
            "source_types": [],
            "error": str(exc),
        }, set()


def _run_source_with_v2_fallback(
    name: str,
    source_type: str,
    fn: Callable[[], list[dict]],
    limit: int,
) -> tuple[dict, set[str]]:
    status, source_types = _run_source(name, fn)
    if status["fetch_ok"] or not _is_missing_v1_source_error(Exception(status["error"])):
        return status, source_types

    try:
        rows, attempts = _retry_call(
            lambda: collect_recent_articles_from_v2(source_type=source_type, limit=limit),
            attempts=2,
            base_delay_seconds=0.5,
        )
    except Exception as exc:
        status["fallback_error"] = str(exc)
        return status, source_types

    if not rows:
        status["fallback"] = "analytics_v2"
        status["fallback_fetched"] = 0
        return status, source_types

    fallback_source_types = {str(row.get("source_type") or "") for row in rows if row.get("source_type")}
    return {
        "fetch_ok": True,
        "fetched": len(rows),
        "attempts": status["attempts"] + attempts,
        "source_types": sorted(fallback_source_types),
        "error": "v1_source_missing; fallback=analytics_v2",
        "fallback": "analytics_v2",
    }, fallback_source_types


def run_collector_health_check(
    limit: int = 2,
    github_query: str = "AI agent RAG evaluation language:Python",
    reddit_months: int = 1,
) -> dict:
    """Fetch a tiny sample from every V2 article collector without inserting rows."""
    live_checks = {
        "github": lambda: collect_github_repos(query=github_query, limit=limit),
        "hf": lambda: collect_hf_trending(limit_per_type=limit),
    }
    v1_backed_checks = {
        "news": ("news", lambda: collect_news_from_v1(limit=limit)),
        "reddit": ("reddit", lambda: collect_reddit_from_v1(limit=limit, months=reddit_months)),
        "jobs": ("job", lambda: collect_jobs_from_v1(limit=limit)),
        "papers": ("paper", lambda: collect_papers_from_v1(limit=limit)),
    }
    sources = {}
    covered_source_types: set[str] = set()

    for name, fn in live_checks.items():
        status, source_types = _run_source(name, fn)
        sources[name] = status
        covered_source_types.update(source_types)

    for name, (source_type, fn) in v1_backed_checks.items():
        status, source_types = _run_source_with_v2_fallback(name, source_type, fn, limit=limit)
        sources[name] = status
        covered_source_types.update(source_types)

    missing = validate_article_source_coverage(covered_source_types)
    failed = [name for name, status in sources.items() if not status["fetch_ok"]]
    state = "ok" if not missing and not failed else "degraded"
    result = {
        "state": state,
        "missing_article_sources": missing,
        "failed_collectors": failed,
        "sources": sources,
    }
    logger.info("Collector health: %s", result)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run VectorDBZ V2 source collectors")
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--github-query", default="AI agent RAG evaluation language:Python")
    parser.add_argument("--reddit-months", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args = _parse_args()
    result = run_collector_health_check(
        limit=args.limit,
        github_query=args.github_query,
        reddit_months=args.reddit_months,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["state"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
