"""Small phase-run harness for resilient VectorDBZ V2 pipeline checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRunResult:
    source: str
    critical: bool
    fetch_ok: bool
    fetched: int = 0
    accepted: int = 0
    attempts: int = 1
    error: str = ""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: int = 10
    max_delay_seconds: int = 120

    def delays(self) -> list[int]:
        retry_count = max(self.max_attempts - 1, 0)
        return [
            min(self.base_delay_seconds * (2**idx), self.max_delay_seconds)
            for idx in range(retry_count)
        ]


def evaluate_phase_run(results: list[SourceRunResult]) -> dict:
    """Classify a phase run without hiding source-level failures."""
    blocking_sources: list[str] = []
    degraded_sources: list[str] = []
    warnings: list[str] = []

    for result in results:
        if not result.fetch_ok and result.critical:
            blocking_sources.append(result.source)
            continue
        if not result.fetch_ok:
            degraded_sources.append(result.source)
            continue

        if result.source == "job_market" and result.fetched == 0:
            warnings.append("job_market:no_recent_jobs")
        elif result.fetched > 0 and result.accepted == 0:
            warnings.append(f"{result.source}:all_filtered")

    if blocking_sources:
        state = "failed"
        can_publish = False
    elif degraded_sources:
        state = "degraded"
        can_publish = True
    else:
        state = "ok"
        can_publish = True

    return {
        "state": state,
        "can_publish": can_publish,
        "blocking_sources": blocking_sources,
        "degraded_sources": degraded_sources,
        "warnings": warnings,
        "sources": [
            {
                "source": item.source,
                "critical": item.critical,
                "fetch_ok": item.fetch_ok,
                "fetched": item.fetched,
                "accepted": item.accepted,
                "attempts": item.attempts,
                "error": item.error,
            }
            for item in results
        ],
    }


def watchdog_alerts(
    health_history: list[dict],
    repeated_failure_threshold: int = 3,
) -> list[str]:
    """Derive operational alerts from recent persisted source-health states."""
    failure_counts: dict[str, int] = {}
    alerts: list[str] = []

    for health in health_history:
        for source in health.get("blocking_sources", []):
            failure_counts[source] = failure_counts.get(source, 0) + 1
        for warning in health.get("warnings", []):
            if warning == "job_market:no_recent_jobs":
                alerts.append("empty_critical_source:job_market")

    for source, count in sorted(failure_counts.items()):
        if count >= repeated_failure_threshold:
            alerts.append(f"repeated_failure:{source}")

    return sorted(set(alerts))
