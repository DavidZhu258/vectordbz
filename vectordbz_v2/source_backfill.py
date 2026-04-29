"""Date-window backfill from V1 analytics tables into V2 articles."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, timedelta
from typing import Callable

from .collectors import enrich_paper_row, job_rows_to_articles, reddit_rows_to_articles
from .db import ch_insert_articles, get_ch_v1
from .migrate import _news_row_to_article, _paper_row_to_article

logger = logging.getLogger("vectordbz_v2.source_backfill")

SOURCE_NAMES = ("papers", "news", "reddit", "jobs")


def build_source_query(
    source: str,
    start_date: date,
    end_date: date,
    per_day_limit: int = 20,
) -> str:
    """Build a V1 ClickHouse query for a source-aware historical window."""
    start = start_date.isoformat()
    end = end_date.isoformat()

    if source == "papers":
        limit = _limit_by_clause(per_day_limit, "update_date")
        return f"""
            SELECT arxiv_id, title, abstract, authors, primary_category, categories, pdf_url,
                   update_date, created_at, citation_count, hf_upvotes, github_stars,
                   venue, paper_type, data_source
            FROM papers
            WHERE update_date >= toDate('{start}') AND update_date <= toDate('{end}')
              AND length(arxiv_id) > 0 AND length(title) > 0
            ORDER BY update_date DESC, citation_count DESC, hf_upvotes DESC, github_stars DESC
            {limit}
        """

    if source == "news":
        limit = _limit_by_clause(per_day_limit, "toDate(created_at)")
        return f"""
            SELECT event_id, title, body, url, source, collected_at, created_at, keywords, metadata
            FROM news
            WHERE toDate(created_at) >= toDate('{start}') AND toDate(created_at) <= toDate('{end}')
            ORDER BY toDate(created_at) DESC, collected_at DESC
            {limit}
        """

    if source == "reddit":
        limit = _limit_by_clause(per_day_limit, "toDate(created_at)")
        return f"""
            SELECT event_id, title, body, url, subreddit, author, score, num_comments, upvote_ratio, created_at
            FROM media_reddit_post
            WHERE toDate(created_at) >= toDate('{start}') AND toDate(created_at) <= toDate('{end}')
              AND (length(title) > 0 OR length(body) > 0)
            ORDER BY toDate(created_at) DESC, score DESC, num_comments DESC
            {limit}
        """

    if source == "jobs":
        limit = _limit_by_clause(per_day_limit, "posted_date")
        return f"""
            SELECT job_id, title, company, location, salary, description, source_url, source_name, posted_date, skills
            FROM jobs
            WHERE posted_date >= toDate('{start}') AND posted_date <= toDate('{end}')
              AND length(job_id) > 0 AND length(title) > 0
            ORDER BY posted_date DESC, created_at DESC
            {limit}
        """

    raise ValueError(f"Unsupported source: {source}")


def _limit_by_clause(per_day_limit: int, date_expr: str) -> str:
    if per_day_limit <= 0:
        return ""
    return f"LIMIT {per_day_limit} BY {date_expr}"


def rows_to_articles(source: str, rows: list[tuple]) -> list[dict]:
    if source == "papers":
        articles = [article for row in rows if (article := _paper_row_to_article(row))]
        return [enrich_paper_row(article) for article in articles]
    if source == "news":
        return [_news_row_to_article(row) for row in rows]
    if source == "reddit":
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
    if source == "jobs":
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
    raise ValueError(f"Unsupported source: {source}")


def run_historical_backfill(
    start_date: date,
    end_date: date,
    per_day_limit: int = 20,
    sources: list[str] | None = None,
    dry_run: bool = False,
    batch_size: int = 500,
    ch_v1=None,
    insert_articles: Callable[[list[dict]], int] = ch_insert_articles,
) -> dict:
    """Backfill a historical date window from V1 into V2 articles."""
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    source_names = sources or list(SOURCE_NAMES)
    unsupported = sorted(set(source_names) - set(SOURCE_NAMES))
    if unsupported:
        raise ValueError(f"Unsupported sources: {unsupported}")

    client = ch_v1 or get_ch_v1()
    selected_rows: dict[str, int] = {}
    articles_selected = 0
    articles_inserted = 0

    for source in source_names:
        selected_rows[source] = 0
        for rows in _iter_source_rows(
            client=client,
            source=source,
            start_date=start_date,
            end_date=end_date,
            per_day_limit=per_day_limit,
            batch_size=batch_size,
        ):
            selected_rows[source] += len(rows)
            articles = rows_to_articles(source, rows)
            articles_selected += len(articles)
            if not dry_run:
                articles_inserted += insert_articles(articles)

    result = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "per_day_limit": per_day_limit,
        "sources": source_names,
        "selected_rows": selected_rows,
        "articles_selected": articles_selected,
        "articles_inserted": articles_inserted,
        "dry_run": dry_run,
    }
    logger.info("Historical backfill result: %s", result)
    return result


def _iter_source_rows(
    client,
    source: str,
    start_date: date,
    end_date: date,
    per_day_limit: int,
    batch_size: int,
):
    if per_day_limit > 0:
        yield client.query(build_source_query(source, start_date, end_date, per_day_limit)).result_rows
        return

    current = start_date
    while current <= end_date:
        offset = 0
        while True:
            page_sql = (
                build_source_query(source, current, current, per_day_limit=0)
                + f"\nLIMIT {batch_size} OFFSET {offset}"
            )
            rows = client.query(page_sql).result_rows
            if not rows:
                break
            yield rows
            if len(rows) < batch_size:
                break
            offset += batch_size
        current += timedelta(days=1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill V1 source rows into VectorDBZ V2 articles")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--per-day-limit", type=int, default=20, help="0 means no per-day cap")
    parser.add_argument("--source", action="append", choices=SOURCE_NAMES, help="Repeatable source filter")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=500)
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args = _parse_args()
    result = run_historical_backfill(
        start_date=date.fromisoformat(args.start),
        end_date=date.fromisoformat(args.end),
        per_day_limit=args.per_day_limit,
        sources=args.source,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
