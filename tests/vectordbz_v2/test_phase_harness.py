from vectordbz_v2.phase_harness import (
    SourceRunResult,
    RetryPolicy,
    watchdog_alerts,
    evaluate_phase_run,
)


def test_phase_run_blocks_when_a_critical_source_fetch_fails():
    verdict = evaluate_phase_run(
        [
            SourceRunResult(source="job_market", critical=True, fetch_ok=True, fetched=12, accepted=8),
            SourceRunResult(source="paper_top_venue", critical=True, fetch_ok=False, error="timeout"),
            SourceRunResult(source="hf_model", critical=False, fetch_ok=True, fetched=20, accepted=5),
        ]
    )

    assert verdict["state"] == "failed"
    assert verdict["can_publish"] is False
    assert verdict["blocking_sources"] == ["paper_top_venue"]


def test_phase_run_can_publish_when_optional_source_fails_with_degraded_state():
    verdict = evaluate_phase_run(
        [
            SourceRunResult(source="job_market", critical=True, fetch_ok=True, fetched=4, accepted=2),
            SourceRunResult(source="paper_top_venue", critical=True, fetch_ok=True, fetched=6, accepted=3),
            SourceRunResult(source="hf_model", critical=False, fetch_ok=False, error="rate limited"),
        ]
    )

    assert verdict["state"] == "degraded"
    assert verdict["can_publish"] is True
    assert "hf_model" in verdict["degraded_sources"]


def test_empty_job_market_is_publishable_but_reported_as_market_signal():
    verdict = evaluate_phase_run(
        [
            SourceRunResult(source="job_market", critical=True, fetch_ok=True, fetched=0, accepted=0),
            SourceRunResult(source="paper_top_venue", critical=True, fetch_ok=True, fetched=8, accepted=5),
        ]
    )

    assert verdict["state"] == "ok"
    assert verdict["can_publish"] is True
    assert "job_market:no_recent_jobs" in verdict["warnings"]


def test_retry_policy_uses_bounded_exponential_backoff():
    policy = RetryPolicy(max_attempts=4, base_delay_seconds=5, max_delay_seconds=30)

    assert policy.delays() == [5, 10, 20]


def test_watchdog_alerts_flag_repeated_failures_and_empty_critical_sources():
    alerts = watchdog_alerts(
        [
            {"state": "failed", "blocking_sources": ["job_market"], "warnings": []},
            {"state": "failed", "blocking_sources": ["job_market"], "warnings": []},
            {"state": "ok", "blocking_sources": [], "warnings": ["job_market:no_recent_jobs"]},
        ],
        repeated_failure_threshold=2,
    )

    assert "repeated_failure:job_market" in alerts
    assert "empty_critical_source:job_market" in alerts
