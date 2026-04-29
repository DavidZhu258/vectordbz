"""
VectorDBZ V2 — Data Migration Script
Migrate V1 analytics.* → V2 analytics_v2.articles (one-time)

Migrates: papers, news, media_reddit_post, jobs, hf_trending
Does NOT modify V1 data — read-only.
"""
import json
import logging
from datetime import date, datetime, time, timezone

from .db import get_ch, get_ch_v1, ch_insert_articles

logger = logging.getLogger("vectordbz_v2.migrate")

BATCH_SIZE = 5000
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _to_datetime(val) -> datetime:
    """Safely convert date/datetime/None → datetime for DateTime64(3)."""
    if val is None:
        return EPOCH
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    if isinstance(val, date):
        return datetime.combine(val, time.min, tzinfo=timezone.utc)
    return EPOCH


def _snippet(value: str, limit: int = 120) -> str:
    return " ".join((value or "").split())[:limit]

logger = logging.getLogger("vectordbz_v2.migrate")

BATCH_SIZE = 5000


def _migration_page_size(limit: int, total: int, batch_size: int = BATCH_SIZE) -> int:
    """Return the next SELECT page size for bounded and full migrations."""
    if limit <= 0:
        return batch_size
    remaining = limit - total
    if remaining <= 0:
        return 0
    return min(batch_size, remaining)


def _parse_metadata_json(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _source_type_for_news(source: str, url: str, metadata: dict) -> str:
    source_norm = (source or metadata.get("source") or "").lower()
    url_norm = (url or "").lower()

    if source_norm in {"github", "github_repo"} or "github.com/" in url_norm:
        return "github_repo"

    if source_norm in {"hf_model", "hf_dataset", "hf_space"}:
        return source_norm

    if source_norm == "hf_trending" or "huggingface.co/" in url_norm:
        category = str(metadata.get("category") or metadata.get("repo_type") or "").lower()
        if category in {"dataset", "datasets"} or "huggingface.co/datasets/" in url_norm:
            return "hf_dataset"
        if category in {"space", "spaces"} or "huggingface.co/spaces/" in url_norm:
            return "hf_space"
        return "hf_model"

    return "news"


def _news_row_to_article(row: tuple) -> dict:
    (event_id, title, body, url, source,
     collected_at, created_at, keywords, meta_str) = row

    metadata = _parse_metadata_json(meta_str)
    metadata.update({
        "source": source or metadata.get("source", ""),
        "keywords": keywords if keywords else [],
    })

    return {
        "source_type": _source_type_for_news(source, url, metadata),
        "source_id": event_id,
        "published_at": _to_datetime(created_at),
        "collected_at": _to_datetime(collected_at),
        "title": title or "",
        "content": body or "",
        "author": "",
        "source_url": url or "",
        "metadata": metadata,
    }


def migrate_papers(limit: int = 0):
    """Migrate analytics.papers → analytics_v2.articles (source_type=paper)"""
    ch_v1 = get_ch_v1()
    
    offset = 0
    total = 0

    logger.info("Starting papers migration...")

    while True:
        page_size = _migration_page_size(limit, total)
        if page_size == 0:
            break

        rows = ch_v1.query(
            f"SELECT arxiv_id, title, abstract, authors, "
            f"primary_category, categories, pdf_url, "
            f"update_date, created_at, citation_count, "
            f"hf_upvotes, github_stars "
            f"FROM papers "
            f"WHERE length(arxiv_id) > 0 AND length(title) > 0 "
            f"ORDER BY created_at DESC "
            f"LIMIT {page_size} "
            f"OFFSET {offset}"
        ).result_rows

        if not rows:
            break

        articles = [article for r in rows if (article := _paper_row_to_article(r))]

        ch_insert_articles(articles)
        total += len(articles)
        offset += page_size
        logger.info(f"Papers migrated: {total}")

        if limit > 0 and total >= limit:
            break

    logger.info(f"Papers migration complete: {total} rows")
    return total


def _paper_row_to_article(row: tuple) -> dict | None:
    (arxiv_id, title, abstract, authors,
     primary_cat, categories, pdf_url,
     update_date, created_at, citations,
     hf_upvotes, github_stars, *extra) = row
    venue = extra[0] if len(extra) > 0 else ""
    paper_type = extra[1] if len(extra) > 1 else ""
    data_source = extra[2] if len(extra) > 2 else ""

    if not arxiv_id or not title:
        return None

    return {
        "source_type": "paper",
        "source_id": arxiv_id,
        "published_at": _to_datetime(update_date),
        "collected_at": _to_datetime(created_at),
        "title": title or "",
        "content": abstract or "",
        "author": authors or "",
        "source_url": pdf_url or f"https://arxiv.org/abs/{arxiv_id}",
        "metadata": {
            "primary_category": primary_cat or "",
            "categories": categories or "",
            "citation_count": citations or 0,
            "hf_upvotes": hf_upvotes or 0,
            "github_stars": github_stars or 0,
            "venue": venue or "",
            "paper_type": paper_type or "",
            "data_source": data_source or "",
        },
    }


def migrate_news(limit: int = 0):
    """Migrate analytics.news → analytics_v2.articles (source_type=news)"""
    ch_v1 = get_ch_v1()
    
    offset = 0
    total = 0

    logger.info("Starting news migration...")

    while True:
        page_size = _migration_page_size(limit, total)
        if page_size == 0:
            break

        rows = ch_v1.query(
            f"SELECT event_id, title, body, url, source, "
            f"collected_at, created_at, keywords, metadata "
            f"FROM news "
            f"ORDER BY created_at DESC "
            f"LIMIT {page_size} "
            f"OFFSET {offset}"
        ).result_rows

        if not rows:
            break

        articles = [_news_row_to_article(r) for r in rows]

        ch_insert_articles(articles)
        total += len(articles)
        offset += page_size
        logger.info(f"News migrated: {total}")

        if limit > 0 and total >= limit:
            break

    logger.info(f"News migration complete: {total} rows")
    return total


def migrate_reddit(limit: int = 0, months: int = 6):
    """
    Migrate analytics.media_reddit_post → analytics_v2.articles (source_type=reddit)
    Default: only last 6 months to keep V2 lean.
    """
    ch_v1 = get_ch_v1()
    
    offset = 0
    total = 0
    conditions = ["(length(title) > 0 OR length(body) > 0)"]
    if months > 0:
        conditions.insert(0, f"created_at >= now() - INTERVAL {months} MONTH")
    time_filter = "WHERE " + " AND ".join(conditions)

    logger.info(f"Starting reddit migration (last {months} months)...")

    while True:
        page_size = _migration_page_size(limit, total)
        if page_size == 0:
            break

        rows = ch_v1.query(
            f"SELECT event_id, title, body, url, subreddit, "
            f"author, score, num_comments, upvote_ratio, "
            f"created_at, fetched_at "
            f"FROM media_reddit_post "
            f"{time_filter} "
            f"ORDER BY created_at DESC "
            f"LIMIT {page_size} "
            f"OFFSET {offset}"
        ).result_rows

        if not rows:
            break

        articles = [article for r in rows if (article := _reddit_row_to_article(r))]

        ch_insert_articles(articles)
        total += len(articles)
        offset += page_size
        logger.info(f"Reddit migrated: {total}")

        if limit > 0 and total >= limit:
            break

    logger.info(f"Reddit migration complete: {total} rows")
    return total


def _reddit_row_to_article(row: tuple) -> dict | None:
    (event_id, title, body, url, subreddit,
     author, score, num_comments, upvote_ratio,
     created_at, fetched_at) = row

    if not event_id:
        return None

    display_title = _snippet(title)
    if not display_title and body:
        display_title = f"[r/{subreddit or 'reddit'}] {_snippet(body)}"
    if not display_title:
        return None

    return {
        "source_type": "reddit",
        "source_id": event_id,
        "published_at": _to_datetime(created_at),
        "collected_at": _to_datetime(fetched_at),
        "title": display_title,
        "content": body or "",
        "author": author or "",
        "source_url": url or "",
        "metadata": {
            "subreddit": subreddit or "",
            "score": score or 0,
            "num_comments": num_comments or 0,
            "upvote_ratio": float(upvote_ratio or 0),
        },
    }


def migrate_jobs(limit: int = 0):
    """Migrate analytics.jobs → analytics_v2.articles (source_type=job)"""
    ch_v1 = get_ch_v1()
    
    offset = 0
    total = 0

    logger.info("Starting jobs migration...")

    while True:
        page_size = _migration_page_size(limit, total)
        if page_size == 0:
            break

        rows = ch_v1.query(
            f"SELECT job_id, title, company, location, salary, "
            f"description, source_url, source_name, "
            f"posted_date, created_at, skills "
            f"FROM jobs "
            f"ORDER BY created_at DESC "
            f"LIMIT {page_size} "
            f"OFFSET {offset}"
        ).result_rows

        if not rows:
            break

        articles = [_job_row_to_article(r) for r in rows]

        ch_insert_articles(articles)
        total += len(articles)
        offset += page_size
        logger.info(f"Jobs migrated: {total}")

        if limit > 0 and total >= limit:
            break

    logger.info(f"Jobs migration complete: {total} rows")
    return total


def _job_row_to_article(row: tuple) -> dict:
    (job_id, title, company, location, salary,
     description, source_url, source_name,
     posted_date, created_at, skills) = row

    return {
        "source_type": "job",
        "source_id": job_id,
        "published_at": _to_datetime(posted_date),
        "collected_at": _to_datetime(created_at),
        "title": title or "",
        "content": description or "",
        "author": company or "",
        "source_url": source_url or "",
        "metadata": {
            "company": company or "",
            "location": location or "",
            "salary": salary or "",
            "source_name": source_name or "",
            "skills": skills or "",
        },
    }


def migrate_hf_trending(limit: int = 0):
    """Migrate analytics.hf_trending → analytics_v2.articles (source_type=hf_trending)"""
    ch_v1 = get_ch_v1()

    logger.info("Starting HF trending migration...")

    rows = ch_v1.query(
        "SELECT * FROM hf_trending"
        + (f" LIMIT {limit}" if limit > 0 else "")
    ).result_rows

    # hf_trending schema varies — handle dynamically
    columns = ch_v1.query(
        "SELECT name FROM system.columns WHERE database='analytics' AND table='hf_trending' ORDER BY position"
    ).result_rows
    col_names = [c[0] for c in columns]

    articles = []
    for r in rows:
        row_dict = dict(zip(col_names, r))
        articles.append({
            "source_type": "hf_trending",
            "source_id": row_dict.get("model_id", row_dict.get("id", str(hash(str(r))))),
            "collected_at": row_dict.get("collected_at", datetime.now(timezone.utc)),
            "title": row_dict.get("model_id", row_dict.get("title", "")),
            "content": "",
            "source_url": "",
            "metadata": {k: str(v) for k, v in row_dict.items()},
        })

    if articles:
        ch_insert_articles(articles)

    logger.info(f"HF trending migration complete: {len(articles)} rows")
    return len(articles)


def run_full_migration(reddit_months: int = 6):
    """Run all migrations."""
    results = {}
    results["papers"] = migrate_papers()
    results["news"] = migrate_news()
    results["reddit"] = migrate_reddit(months=reddit_months)
    results["jobs"] = migrate_jobs()
    results["hf_trending"] = migrate_hf_trending()

    logger.info(f"Full migration complete: {results}")
    return results


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="VectorDBZ V2 Data Migration")
    parser.add_argument("--source", choices=["papers", "news", "reddit", "jobs", "hf", "all"],
                        default="all", help="Which source to migrate")
    parser.add_argument("--limit", type=int, default=0, help="Limit rows (0=all)")
    parser.add_argument("--reddit-months", type=int, default=6, help="Reddit: only last N months")
    args = parser.parse_args()

    if args.source == "all":
        run_full_migration(reddit_months=args.reddit_months)
    elif args.source == "papers":
        migrate_papers(limit=args.limit)
    elif args.source == "news":
        migrate_news(limit=args.limit)
    elif args.source == "reddit":
        migrate_reddit(limit=args.limit, months=args.reddit_months)
    elif args.source == "jobs":
        migrate_jobs(limit=args.limit)
    elif args.source == "hf":
        migrate_hf_trending(limit=args.limit)
