from datetime import date

from vectordbz_v2.checkpoint import save_phase_checkpoint
from vectordbz_v2 import long_task_runner


def test_run_long_task_records_phase_results_and_persists_final_health(monkeypatch):
    calls = []
    persisted = []

    monkeypatch.setattr(
        long_task_runner,
        "run_embed_worker",
        lambda batch_size, max_articles, mode: calls.append("embed") or (3, 0),
    )
    monkeypatch.setattr(
        long_task_runner,
        "run_rerank_worker",
        lambda themes, days, run_date: calls.append("rerank") or 5,
    )

    def fake_trend(run_date, period_type, source_health):
        calls.append(("trend", source_health["state"]))
        return {"report_json": {"stats": {"total_articles": 5}}}

    monkeypatch.setattr(long_task_runner, "run_trend_analyzer", fake_trend)
    monkeypatch.setattr(
        long_task_runner,
        "ch_insert_source_health",
        lambda health, run_date=None: persisted.append((health, run_date)) or len(health["sources"]) + 1,
    )

    result = long_task_runner.run_long_task_pipeline(
        run_date=date(2026, 4, 28),
        embed_max=3,
        embed_batch=2,
        themes=["agents"],
        rerank_days=7,
        persist_health=True,
    )

    assert calls == ["embed", "rerank", ("trend", "ok")]
    assert result["state"] == "ok"
    assert result["can_publish"] is True
    assert [source["source"] for source in result["sources"]] == [
        "embedding",
        "rerank",
        "trend_report",
    ]
    assert persisted[-1] == (result, date(2026, 4, 28))


def test_run_long_task_can_include_source_collector_phase(monkeypatch):
    calls = []

    monkeypatch.setattr(
        long_task_runner,
        "run_source_collectors",
        lambda github_limit, hf_limit_per_type: calls.append("collect")
        or long_task_runner.SourceRunResult("source_collectors", False, True, fetched=2, accepted=2),
    )
    monkeypatch.setattr(
        long_task_runner,
        "run_embed_worker",
        lambda batch_size, max_articles, mode: calls.append("embed") or (2, 0),
    )
    monkeypatch.setattr(
        long_task_runner,
        "run_rerank_worker",
        lambda themes, days, run_date: calls.append("rerank") or 2,
    )
    monkeypatch.setattr(
        long_task_runner,
        "run_trend_analyzer",
        lambda run_date, period_type, source_health: calls.append("trend") or {"ok": True},
    )
    monkeypatch.setattr(long_task_runner, "ch_insert_source_health", lambda *args, **kwargs: 0)

    result = long_task_runner.run_long_task_pipeline(
        run_date=date(2026, 4, 28),
        collect_live=True,
        github_limit=1,
        hf_limit_per_type=1,
        themes=["agents"],
    )

    assert calls == ["collect", "embed", "rerank", "trend"]
    assert result["sources"][0]["source"] == "source_collectors"


def test_run_long_task_stops_before_report_when_critical_phase_fails(monkeypatch):
    calls = []

    monkeypatch.setattr(
        long_task_runner,
        "run_embed_worker",
        lambda batch_size, max_articles, mode: (0, 2),
    )
    monkeypatch.setattr(
        long_task_runner,
        "run_rerank_worker",
        lambda themes, days, run_date: calls.append("rerank") or 0,
    )
    monkeypatch.setattr(
        long_task_runner,
        "run_trend_analyzer",
        lambda **kwargs: calls.append("trend") or {},
    )
    monkeypatch.setattr(long_task_runner, "ch_insert_source_health", lambda *args, **kwargs: 0)

    result = long_task_runner.run_long_task_pipeline(
        run_date=date(2026, 4, 28),
        embed_max=2,
        embed_batch=2,
        themes=["agents"],
        rerank_days=7,
        persist_health=True,
    )

    assert result["state"] == "failed"
    assert result["blocking_sources"] == ["embedding"]
    assert calls == []


def test_run_long_task_resume_skips_completed_embedding_phase(monkeypatch, tmp_path):
    checkpoint_path = tmp_path / "run.json"
    save_phase_checkpoint(
        checkpoint_path,
        run_date=date(2026, 4, 28),
        phase="embedding",
        result={
            "source": "embedding",
            "critical": True,
            "fetch_ok": True,
            "fetched": 12,
            "accepted": 12,
            "attempts": 1,
            "error": "",
            "duration_seconds": 0.1,
        },
    )
    calls = []

    monkeypatch.setattr(
        long_task_runner,
        "run_embed_worker",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("embedding should be skipped")),
    )
    monkeypatch.setattr(
        long_task_runner,
        "run_rerank_worker",
        lambda themes, days, run_date: calls.append("rerank") or 5,
    )
    monkeypatch.setattr(
        long_task_runner,
        "run_trend_analyzer",
        lambda run_date, period_type, source_health: calls.append("trend") or {"ok": True},
    )
    monkeypatch.setattr(long_task_runner, "ch_insert_source_health", lambda *args, **kwargs: 0)

    result = long_task_runner.run_long_task_pipeline(
        run_date=date(2026, 4, 28),
        embed_max=12,
        embed_batch=4,
        themes=["agents"],
        checkpoint_path=checkpoint_path,
        resume=True,
        persist_health=False,
    )

    assert calls == ["rerank", "trend"]
    assert result["sources"][0]["source"] == "embedding"
    assert result["sources"][0]["accepted"] == 12
    assert result["state"] == "ok"
