"""Long-task phase runner for the VectorDBZ V2 pipeline."""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date
from typing import Any

from .checkpoint import completed_phase_result, load_checkpoint, save_phase_checkpoint
from .collectors import run_source_collectors
from .db import ch_insert_source_health
from .embed_worker import run_embed_worker
from .phase_harness import SourceRunResult, evaluate_phase_run
from .rerank_worker import DEFAULT_THEMES, run_rerank_worker
from .trend_analyzer import run_trend_analyzer

logger = logging.getLogger("vectordbz_v2.long_task")


def _result_dict(result: SourceRunResult, started: float, finished: float) -> dict[str, Any]:
    return {
        "source": result.source,
        "critical": result.critical,
        "fetch_ok": result.fetch_ok,
        "fetched": result.fetched,
        "accepted": result.accepted,
        "attempts": result.attempts,
        "error": result.error,
        "duration_seconds": round(finished - started, 3),
    }


def _evaluate(results: list[dict[str, Any]]) -> dict[str, Any]:
    source_results = [
        SourceRunResult(
            source=item["source"],
            critical=bool(item["critical"]),
            fetch_ok=bool(item["fetch_ok"]),
            fetched=int(item.get("fetched", 0)),
            accepted=int(item.get("accepted", 0)),
            attempts=int(item.get("attempts", 1)),
            error=str(item.get("error", "")),
        )
        for item in results
    ]
    verdict = evaluate_phase_run(source_results)
    by_source = {item["source"]: item for item in results}
    verdict["sources"] = [
        {**source, **({"duration_seconds": by_source[source["source"]]["duration_seconds"]})}
        for source in verdict["sources"]
    ]
    return verdict


def _run_embedding(embed_batch: int, embed_max: int, embed_mode: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        embedded, failed = run_embed_worker(
            batch_size=embed_batch,
            max_articles=embed_max,
            mode=embed_mode,
        )
        result = SourceRunResult(
            source="embedding",
            critical=True,
            fetch_ok=failed == 0,
            fetched=embedded + failed,
            accepted=embedded,
            attempts=1,
            error="" if failed == 0 else f"{failed} embeddings failed",
        )
    except Exception as exc:
        result = SourceRunResult("embedding", True, False, attempts=1, error=str(exc))
    return _result_dict(result, started, time.monotonic())


def _run_rerank(themes: list[str], rerank_days: int, run_date: date) -> dict[str, Any]:
    started = time.monotonic()
    try:
        count = run_rerank_worker(themes=themes, days=rerank_days, run_date=run_date)
        result = SourceRunResult(
            source="rerank",
            critical=True,
            fetch_ok=count > 0,
            fetched=count,
            accepted=count,
            attempts=1,
            error="" if count > 0 else "no rerank results",
        )
    except Exception as exc:
        result = SourceRunResult("rerank", True, False, attempts=1, error=str(exc))
    return _result_dict(result, started, time.monotonic())


def _run_report(run_date: date, period_type: str, source_health: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    try:
        report = run_trend_analyzer(
            run_date=run_date,
            period_type=period_type,
            source_health=source_health,
        )
        result = SourceRunResult(
            source="trend_report",
            critical=True,
            fetch_ok=report is not None,
            fetched=1 if report else 0,
            accepted=1 if report else 0,
            attempts=1,
            error="" if report else "report generation returned None",
        )
    except Exception as exc:
        result = SourceRunResult("trend_report", True, False, attempts=1, error=str(exc))
    return _result_dict(result, started, time.monotonic())


def run_long_task_pipeline(
    run_date: date | None = None,
    collect_live: bool = False,
    github_limit: int = 10,
    hf_limit_per_type: int = 10,
    embed_max: int = 5000,
    embed_batch: int = 64,
    embed_mode: str = "production",
    themes: list[str] | None = None,
    rerank_days: int = 30,
    period_type: str = "daily",
    persist_health: bool = True,
    checkpoint_path: str | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """Run the bounded V2 phase pipeline and persist source health."""
    run_date = run_date or date.today()
    themes = themes or DEFAULT_THEMES
    results: list[dict[str, Any]] = []
    checkpoint = load_checkpoint(checkpoint_path, run_date=run_date) if resume else {
        "run_date": run_date.isoformat(),
        "phases": {},
    }

    if collect_live:
        logger.info("Long-task phase started: source collectors")
        collector_phase = _phase_result_or_run(
            phase="source_collectors",
            checkpoint=checkpoint,
            checkpoint_path=checkpoint_path,
            run_date=run_date,
            runner=lambda: _run_source_collectors(github_limit, hf_limit_per_type),
        )
        results.append(collector_phase)

    logger.info("Long-task phase started: embedding")
    results.append(_phase_result_or_run(
        phase="embedding",
        checkpoint=checkpoint,
        checkpoint_path=checkpoint_path,
        run_date=run_date,
        runner=lambda: _run_embedding(embed_batch, embed_max, embed_mode),
    ))
    interim = _evaluate(results)
    if not interim["can_publish"]:
        if persist_health:
            ch_insert_source_health(interim, run_date=run_date)
        return interim

    logger.info("Long-task phase started: rerank")
    results.append(_phase_result_or_run(
        phase="rerank",
        checkpoint=checkpoint,
        checkpoint_path=checkpoint_path,
        run_date=run_date,
        runner=lambda: _run_rerank(themes, rerank_days, run_date),
    ))
    interim = _evaluate(results)
    if not interim["can_publish"]:
        if persist_health:
            ch_insert_source_health(interim, run_date=run_date)
        return interim

    logger.info("Long-task phase started: trend report")
    results.append(_phase_result_or_run(
        phase="trend_report",
        checkpoint=checkpoint,
        checkpoint_path=checkpoint_path,
        run_date=run_date,
        runner=lambda: _run_report(run_date, period_type, interim),
    ))
    final_health = _evaluate(results)

    if persist_health:
        ch_insert_source_health(final_health, run_date=run_date)

    return final_health


def _run_source_collectors(github_limit: int, hf_limit_per_type: int) -> dict[str, Any]:
    started = time.monotonic()
    collector_result = run_source_collectors(
        github_limit=github_limit,
        hf_limit_per_type=hf_limit_per_type,
    )
    return _result_dict(collector_result, started, time.monotonic())


def _phase_result_or_run(
    phase: str,
    checkpoint: dict[str, Any],
    checkpoint_path: str | None,
    run_date: date,
    runner,
) -> dict[str, Any]:
    completed = completed_phase_result(checkpoint, phase)
    if completed is not None:
        logger.info("Long-task phase resumed from checkpoint: %s", phase)
        return completed
    result = runner()
    save_phase_checkpoint(checkpoint_path, run_date=run_date, phase=phase, result=result)
    checkpoint.setdefault("phases", {})[phase] = result
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run VectorDBZ V2 long-task pipeline")
    parser.add_argument("--date", default=None, help="Run date in YYYY-MM-DD format")
    parser.add_argument("--collect-live", action="store_true")
    parser.add_argument("--github-limit", type=int, default=10)
    parser.add_argument("--hf-limit-per-type", type=int, default=10)
    parser.add_argument("--embed-max", type=int, default=5000)
    parser.add_argument("--embed-batch", type=int, default=64)
    parser.add_argument("--embed-mode", choices=["production", "bulk"], default="production")
    parser.add_argument("--rerank-days", type=int, default=30)
    parser.add_argument("--theme", action="append", default=None, help="Theme to rerank; repeatable")
    parser.add_argument("--period", choices=["daily", "weekly", "monthly"], default="daily")
    parser.add_argument("--no-persist-health", action="store_true")
    parser.add_argument("--checkpoint-path", default=None)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args = _parse_args()
    run_date = date.fromisoformat(args.date) if args.date else date.today()
    result = run_long_task_pipeline(
        run_date=run_date,
        collect_live=args.collect_live,
        github_limit=args.github_limit,
        hf_limit_per_type=args.hf_limit_per_type,
        embed_max=args.embed_max,
        embed_batch=args.embed_batch,
        embed_mode=args.embed_mode,
        themes=args.theme,
        rerank_days=args.rerank_days,
        period_type=args.period,
        persist_health=not args.no_persist_health,
        checkpoint_path=args.checkpoint_path,
        resume=args.resume,
    )
    print(result)
    return 0 if result.get("can_publish") else 1


if __name__ == "__main__":
    raise SystemExit(main())
