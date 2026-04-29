"""Evidence-first signal and cited Q&A contract helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .source_taxonomy import parse_metadata


def build_evidence_signal(
    signal: dict[str, Any],
    now: datetime | None = None,
    stale_days: int = 14,
) -> dict[str, Any]:
    """Convert a ranked signal into an evidence-backed report item."""
    now = now or datetime.now(timezone.utc)
    metadata = parse_metadata(signal.get("metadata"))
    source_type = str(signal.get("source_type") or "")
    source_id = str(signal.get("source_id") or "")
    evidence_spans = _evidence_spans(signal, source_type, source_id)
    counter_evidence = []
    if not evidence_spans:
        counter_evidence.append("no evidence spans")
    if _is_stale(metadata, now=now, stale_days=stale_days):
        counter_evidence.append(f"stale evidence older than {stale_days} days")

    confidence = _confidence(signal, evidence_spans, counter_evidence)
    return {
        "claim": str(signal.get("title") or "").strip(),
        "why_now": _why_now(signal, metadata),
        "evidence_spans": evidence_spans,
        "counter_evidence": "; ".join(counter_evidence),
        "action": _default_action(signal),
        "confidence": confidence,
        "source_type": source_type,
        "source_id": source_id,
        "source_url": str(signal.get("source_url") or ""),
    }


def build_cited_answer_payload(
    query: str,
    signals: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic cited answer payload for the UI/API layer."""
    evidence_signals = [build_evidence_signal(signal, now=now) for signal in signals]
    usable = [signal for signal in evidence_signals if signal["evidence_spans"]]
    skipped = [signal["source_id"] for signal in evidence_signals if not signal["evidence_spans"]]
    citations = [
        span["evidence_id"]
        for signal in usable
        for span in signal["evidence_spans"][:1]
    ]

    if not usable:
        return {
            "query": query,
            "answer_state": "insufficient_evidence",
            "answer": "Insufficient evidence in the current VectorDBZ corpus to answer this confidently.",
            "citations": [],
            "signals_used": [],
            "signals_skipped": skipped,
            "evidence_signals": evidence_signals,
        }

    claim_list = "; ".join(signal["claim"] for signal in usable[:3])
    caveats = [signal["counter_evidence"] for signal in usable if signal["counter_evidence"]]
    answer = f"{claim_list}."
    if caveats:
        answer += " Caveat: " + "; ".join(caveats) + "."

    return {
        "query": query,
        "answer_state": "answerable",
        "answer": answer,
        "citations": citations,
        "signals_used": [signal["source_id"] for signal in usable],
        "signals_skipped": skipped,
        "evidence_signals": evidence_signals,
    }


def _evidence_spans(signal: dict[str, Any], source_type: str, source_id: str) -> list[dict[str, Any]]:
    source_url = str(signal.get("source_url") or "")
    spans = []
    for idx, text in enumerate(signal.get("evidence") or [], start=1):
        text = str(text).strip()
        if not text:
            continue
        spans.append({
            "evidence_id": f"{source_type}:{source_id}:{idx}",
            "text": text[:500],
            "source_url": source_url,
        })
        if len(spans) >= 5:
            break
    return spans


def _why_now(signal: dict[str, Any], metadata: dict[str, Any]) -> str:
    if metadata.get("selection_reason"):
        return str(metadata["selection_reason"])
    if signal.get("score") is not None:
        return f"ranked score={float(signal.get('score') or 0):.3f}"
    return "included by source-specific ranking"


def _confidence(
    signal: dict[str, Any],
    evidence_spans: list[dict[str, Any]],
    counter_evidence: list[str],
) -> str:
    if not evidence_spans or counter_evidence:
        return "low"
    score = float(signal.get("score") or 0)
    if score >= 0.8 or len(evidence_spans) >= 2:
        return "high"
    return "medium"


def _is_stale(metadata: dict[str, Any], now: datetime, stale_days: int) -> bool:
    value = metadata.get("collected_at") or metadata.get("published_at")
    if not value:
        return False
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
    if not isinstance(value, datetime):
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (now - value).total_seconds() > stale_days * 86400


def _default_action(signal: dict[str, Any]) -> str:
    source_url = str(signal.get("source_url") or "")
    if source_url:
        return "Inspect the cited source before taking action."
    return "Inspect the underlying source record before taking action."
