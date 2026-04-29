from datetime import date

from vectordbz_v2.checkpoint import (
    completed_phase_result,
    load_checkpoint,
    save_phase_checkpoint,
)


def test_checkpoint_roundtrip_tracks_completed_phase(tmp_path):
    checkpoint_path = tmp_path / "run.json"
    result = {
        "source": "embedding",
        "critical": True,
        "fetch_ok": True,
        "fetched": 10,
        "accepted": 10,
        "attempts": 1,
        "error": "",
    }

    save_phase_checkpoint(checkpoint_path, run_date=date(2026, 4, 28), phase="embedding", result=result)
    checkpoint = load_checkpoint(checkpoint_path, run_date=date(2026, 4, 28))

    assert completed_phase_result(checkpoint, "embedding") == result
    assert completed_phase_result(checkpoint, "rerank") is None


def test_checkpoint_ignores_other_run_dates(tmp_path):
    checkpoint_path = tmp_path / "run.json"
    save_phase_checkpoint(
        checkpoint_path,
        run_date=date(2026, 4, 27),
        phase="embedding",
        result={"source": "embedding", "fetch_ok": True},
    )

    checkpoint = load_checkpoint(checkpoint_path, run_date=date(2026, 4, 28))

    assert checkpoint["phases"] == {}
