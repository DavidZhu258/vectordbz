"""Minimal VectorDBZ V2 API for dashboard reuse and deployment health."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .evidence_contract import build_cited_answer_payload


app = FastAPI(title="VectorDBZ V2 API", version="2.0.0")


class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    signals: list[dict[str, Any]] = Field(default_factory=list)


@app.get("/api/v2/health")
def health() -> dict[str, Any]:
    return {
        "service": "vectordbz_v2",
        "state": "ok",
        "external_bind_host": "0.0.0.0",
        "endpoints": [
            "/api/v2/health",
            "/api/v2/ask",
        ],
    }


@app.post("/api/v2/ask")
def ask(request: AskRequest) -> dict[str, Any]:
    return build_cited_answer_payload(
        query=request.query,
        signals=request.signals,
    )
