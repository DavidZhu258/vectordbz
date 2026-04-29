"""JSON checkpoint helpers for resumable V2 long tasks."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def load_checkpoint(path: str | Path | None, run_date: date) -> dict[str, Any]:
    """Load checkpoint for run_date; return an empty checkpoint when absent or stale."""
    if path is None:
        return {"run_date": run_date.isoformat(), "phases": {}}
    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        return {"run_date": run_date.isoformat(), "phases": {}}
    try:
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"run_date": run_date.isoformat(), "phases": {}}
    if payload.get("run_date") != run_date.isoformat():
        return {"run_date": run_date.isoformat(), "phases": {}}
    phases = payload.get("phases")
    return {
        "run_date": run_date.isoformat(),
        "updated_at": payload.get("updated_at", ""),
        "phases": phases if isinstance(phases, dict) else {},
    }


def save_phase_checkpoint(
    path: str | Path | None,
    run_date: date,
    phase: str,
    result: dict[str, Any],
) -> None:
    """Persist one completed phase result."""
    if path is None:
        return
    checkpoint_path = Path(path)
    checkpoint = load_checkpoint(checkpoint_path, run_date=run_date)
    checkpoint["phases"][phase] = result
    checkpoint["updated_at"] = datetime.now(timezone.utc).isoformat()
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def completed_phase_result(checkpoint: dict[str, Any], phase: str) -> dict[str, Any] | None:
    """Return a completed successful phase result if it can be reused."""
    result = (checkpoint.get("phases") or {}).get(phase)
    if not isinstance(result, dict):
        return None
    if result.get("fetch_ok") is not True:
        return None
    return result
