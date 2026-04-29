"""Source-aware live collectors for VectorDBZ V2."""

from __future__ import annotations

import time
import socket
from datetime import date, datetime, timezone
from typing import Any

import requests

from .db import ch_insert_articles, get_ch_v1
from .migrate import _news_row_to_article
from .phase_harness import SourceRunResult
from .source_registry import annotate_article_with_source_rule
from .source_taxonomy import paper_tier

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
HF_BASE_URL = "https://huggingface.co/api"
NO_PROXY = {"http": "", "https": ""}
LOCAL_PROXY_PORTS = (7897, 7890, 1080)


def _retry_call(fn, attempts: int = 3, base_delay_seconds: float = 1.0):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return fn(), attempt
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(base_delay_seconds * (2 ** (attempt - 1)))
    raise last_error


def _is_missing_v1_source_error(exc: Exception) -> bool:
    text = str(exc)
    return "UNKNOWN_TABLE" in text or "Unknown table expression" in text


def _detect_local_proxy() -> dict[str, str] | None:
    for port in LOCAL_PROXY_PORTS:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                proxy_url = f"http://127.0.0.1:{port}"
                return {"http": proxy_url, "https": proxy_url}
        except OSError:
            continue
    return None


def _get_with_network_fallback(url: str, **kwargs):
    primary_proxies = kwargs.get("proxies")
    try:
        return requests.get(url, **kwargs)
    except requests.exceptions.RequestException as first_error:
        fallback_proxy = _detect_local_proxy()
        if not fallback_proxy or primary_proxies == fallback_proxy:
            raise
        fallback_kwargs = dict(kwargs)
        fallback_kwargs["proxies"] = fallback_proxy
        try:
            return requests.get(url, **fallback_kwargs)
        except requests.exceptions.RequestException:
            raise first_error


def _parse_dt(value: str | date | datetime | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def collect_github_repos(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Collect GitHub repositories into V2 article rows."""
    response = requests.get(
        GITHUB_SEARCH_URL,
        params={
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": limit,
        },
        headers={"Accept": "application/vnd.github+json"},
        proxies=NO_PROXY,
        timeout=30,
    )
    response.raise_for_status()
    rows = []
    for item in response.json().get("items", [])[:limit]:
        full_name = item.get("full_name") or item.get("name") or ""
        if not full_name:
            continue
        rows.append({
            "source_type": "github_repo",
            "source_id": full_name,
            "published_at": _parse_dt(item.get("created_at")),
            "collected_at": datetime.now(timezone.utc),
            "title": full_name,
            "content": item.get("description") or "",
            "author": (item.get("owner") or {}).get("login", ""),
            "source_url": item.get("html_url") or f"https://github.com/{full_name}",
            "metadata": {
                "source": "github",
                "stars": item.get("stargazers_count") or 0,
                "forks": item.get("forks_count") or 0,
                "topics": item.get("topics") or [],
                "updated_at": item.get("updated_at") or "",
                "language": item.get("language") or "",
            },
        })
    return rows


def _hf_rows(endpoint: str, source_type: str, limit: int) -> list[dict[str, Any]]:
    response = _get_with_network_fallback(
        f"{HF_BASE_URL}/{endpoint}",
        params={"sort": "likes7d", "direction": "-1", "limit": limit},
        proxies=NO_PROXY,
        timeout=30,
    )
    response.raise_for_status()
    rows = []
    for item in response.json()[:limit]:
        repo_id = item.get("id") or item.get("modelId") or ""
        if not repo_id:
            continue
        rows.append({
            "source_type": source_type,
            "source_id": repo_id,
            "published_at": _parse_dt(item.get("createdAt")),
            "collected_at": datetime.now(timezone.utc),
            "title": repo_id,
            "content": item.get("description") or "",
            "author": repo_id.split("/")[0] if "/" in repo_id else "",
            "source_url": f"https://huggingface.co/{repo_id}",
            "metadata": {
                "source": "hf_trending",
                "category": source_type.removeprefix("hf_"),
                "likes": item.get("likes") or 0,
                "downloads": item.get("downloads") or 0,
                "tags": item.get("tags") or [],
                "sdk": item.get("sdk") or "",
            },
        })
    return rows


def collect_hf_trending(limit_per_type: int = 10) -> list[dict[str, Any]]:
    """Collect HF models, datasets, and spaces into source-aware rows."""
    rows = []
    rows.extend(_hf_rows("models", "hf_model", limit_per_type))
    rows.extend(_hf_rows("datasets", "hf_dataset", limit_per_type))
    rows.extend(_hf_rows("spaces", "hf_space", limit_per_type))
    return rows


def reddit_rows_to_articles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    articles = []
    for row in rows:
        event_id = row.get("event_id") or row.get("id") or ""
        title = row.get("title") or row.get("body") or ""
        subreddit = row.get("subreddit") or "reddit"
        if not event_id or not title:
            continue
        article = {
            "source_type": "reddit",
            "source_id": event_id,
            "published_at": _parse_dt(row.get("created_at")),
            "collected_at": datetime.now(timezone.utc),
            "title": title,
            "content": row.get("body") or "",
            "author": row.get("author") or "",
            "source_url": row.get("url") or "",
            "metadata": {
                "source": "reddit",
                "sub_source": f"reddit:{subreddit}",
                "subreddit": subreddit,
                "score": row.get("score") or 0,
                "num_comments": row.get("num_comments") or row.get("comments") or 0,
                "upvote_ratio": row.get("upvote_ratio") or 0,
            },
        }
        articles.append(annotate_article_with_source_rule(article))
    return articles


def job_rows_to_articles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    articles = []
    for row in rows:
        job_id = row.get("job_id") or row.get("id") or ""
        title = row.get("title") or ""
        if not job_id or not title:
            continue
        articles.append({
            "source_type": "job",
            "source_id": job_id,
            "published_at": _parse_dt(row.get("posted_date")),
            "collected_at": datetime.now(timezone.utc),
            "title": title,
            "content": row.get("description") or "",
            "author": row.get("company") or "",
            "source_url": row.get("source_url") or "",
            "metadata": {
                "source": row.get("source_name") or "jobs",
                "critical_source": True,
                "company": row.get("company") or "",
                "location": row.get("location") or "",
                "salary": row.get("salary") or "",
                "skills": row.get("skills") or "",
            },
        })
    return articles


def enrich_paper_row(row: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(row)
    metadata = dict(enriched.get("metadata") or {})
    tier = paper_tier(metadata)
    if tier in {"A*", "A"}:
        metadata.setdefault("venue_rank", tier)
    enriched["metadata"] = metadata
    return enriched


def collect_news_from_v1(limit: int = 10) -> list[dict[str, Any]]:
    rows = get_ch_v1().query(
        "SELECT event_id, title, body, url, source, collected_at, created_at, keywords, metadata "
        "FROM news "
        "ORDER BY collected_at DESC "
        f"LIMIT {limit}"
    ).result_rows
    return [_news_row_to_article(row) for row in rows]


def collect_reddit_from_v1(limit: int = 10, months: int = 1) -> list[dict[str, Any]]:
    rows = get_ch_v1().query(
        "SELECT event_id, title, body, url, subreddit, author, score, num_comments, upvote_ratio, created_at "
        "FROM media_reddit_post "
        f"WHERE created_at >= now() - INTERVAL {months} MONTH "
        "ORDER BY score DESC "
        f"LIMIT {limit}"
    ).result_rows
    return reddit_rows_to_articles([
        {
            "event_id": row[0],
            "title": row[1],
            "body": row[2],
            "url": row[3],
            "subreddit": row[4],
            "author": row[5],
            "score": row[6],
            "num_comments": row[7],
            "upvote_ratio": row[8],
            "created_at": row[9],
        }
        for row in rows
    ])


def collect_jobs_from_v1(limit: int = 10) -> list[dict[str, Any]]:
    from .db import get_ch_v1

    rows = get_ch_v1().query(
        "SELECT job_id, title, company, location, salary, description, source_url, source_name, posted_date, skills "
        "FROM jobs "
        "ORDER BY created_at DESC "
        f"LIMIT {limit}"
    ).result_rows
    return job_rows_to_articles([
        {
            "job_id": row[0],
            "title": row[1],
            "company": row[2],
            "location": row[3],
            "salary": row[4],
            "description": row[5],
            "source_url": row[6],
            "source_name": row[7],
            "posted_date": row[8],
            "skills": row[9],
        }
        for row in rows
    ])


def collect_papers_from_v1(limit: int = 10) -> list[dict[str, Any]]:
    from .migrate import _paper_row_to_article
    from .db import get_ch_v1

    rows = get_ch_v1().query(
        "SELECT arxiv_id, title, abstract, authors, primary_category, categories, pdf_url, "
        "update_date, created_at, citation_count, hf_upvotes, github_stars "
        "FROM papers "
        "WHERE length(arxiv_id) > 0 AND length(title) > 0 "
        "ORDER BY created_at DESC "
        f"LIMIT {limit}"
    ).result_rows
    articles = [article for row in rows if (article := _paper_row_to_article(row))]
    return [enrich_paper_row(article) for article in articles]


def collect_recent_articles_from_v2(source_type: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return recent V2 article rows for independent deploys without V1 source tables."""
    from .db import get_ch

    safe_source_type = source_type.replace("\\", "\\\\").replace("'", "\\'")
    rows = get_ch().query(
        "SELECT source_type, source_id, title, source_url, metadata "
        "FROM articles FINAL "
        f"WHERE source_type = '{safe_source_type}' "
        "ORDER BY collected_at DESC "
        f"LIMIT {limit}"
    ).result_rows
    return [
        {
            "source_type": row[0],
            "source_id": row[1],
            "title": row[2],
            "source_url": row[3],
            "metadata": row[4],
        }
        for row in rows
    ]


def run_source_collectors(
    github_query: str = "AI agent RAG evaluation language:Python",
    github_limit: int = 10,
    hf_limit_per_type: int = 10,
    news_limit: int = 10,
    reddit_limit: int = 10,
    job_limit: int = 10,
    paper_limit: int = 10,
) -> SourceRunResult:
    """Run live source collectors and insert accepted rows into V2 articles."""
    rows = []
    errors = []
    total_attempts = 0

    try:
        result, attempts = _retry_call(lambda: collect_github_repos(query=github_query, limit=github_limit))
        total_attempts += attempts
        rows.extend(result)
    except Exception as exc:
        total_attempts += 3
        errors.append(f"github:{exc}")

    try:
        result, attempts = _retry_call(lambda: collect_hf_trending(limit_per_type=hf_limit_per_type))
        total_attempts += attempts
        rows.extend(result)
    except Exception as exc:
        total_attempts += 3
        errors.append(f"hf:{exc}")

    warnings = []
    for name, fn in [
        ("news", lambda: collect_news_from_v1(limit=news_limit)),
        ("reddit", lambda: collect_reddit_from_v1(limit=reddit_limit, months=1)),
        ("jobs", lambda: collect_jobs_from_v1(limit=job_limit)),
        ("papers", lambda: collect_papers_from_v1(limit=paper_limit)),
    ]:
        try:
            result, attempts = _retry_call(fn)
            total_attempts += attempts
            rows.extend(result)
        except Exception as exc:
            total_attempts += 3
            if _is_missing_v1_source_error(exc):
                warnings.append(f"{name}:v1_source_missing")
            else:
                errors.append(f"{name}:{exc}")

    accepted = ch_insert_articles(rows) if rows else 0
    return SourceRunResult(
        source="source_collectors",
        critical=False,
        fetch_ok=not errors,
        fetched=len(rows),
        accepted=accepted,
        attempts=total_attempts,
        error="; ".join(errors + warnings),
    )
