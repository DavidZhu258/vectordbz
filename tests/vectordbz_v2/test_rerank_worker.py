from datetime import date

from vectordbz_v2 import rerank_worker


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"scores": [0.2, 0.9]}


def test_deepinfra_rerank_uses_official_queries_payload(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append({"args": args, **kwargs})
        return _Response()

    monkeypatch.setattr(rerank_worker.requests, "post", fake_post)
    monkeypatch.setattr(rerank_worker.config, "LLM_MAX_RETRIES", 1)
    monkeypatch.setattr(rerank_worker.config, "LLM_RETRY_DELAY", 0)

    ranked = rerank_worker.deepinfra_rerank(
        query="agent tools",
        documents=["doc a", "doc b"],
    )

    assert calls[0]["json"] == {
        "queries": ["agent tools"],
        "documents": ["doc a", "doc b"],
    }
    assert ranked[0] == {"index": 1, "score": 0.9}


def test_rerank_theme_preserves_candidate_source_url(monkeypatch):
    monkeypatch.setattr(rerank_worker, "embed_with_fallback", lambda texts, mode, jina_task: ([[0.1] * 512], "jina"))
    monkeypatch.setattr(
        rerank_worker,
        "qdrant_search",
        lambda **kwargs: [
            {
                "id": "p1",
                "score": 0.7,
                "payload": {
                    "source_type": "github_repo",
                    "source_id": "gh-1",
                    "title": "owner/repo",
                    "source_url": "https://github.com/owner/repo",
                },
            }
        ],
    )
    monkeypatch.setattr(
        rerank_worker,
        "deepinfra_rerank",
        lambda query, documents: [{"index": 0, "score": 0.95}],
    )

    rows = rerank_worker.rerank_theme("agent tools", run_date=date(2026, 4, 28))

    assert rows[0]["source_url"] == "https://github.com/owner/repo"


def test_rerank_theme_falls_back_when_jina_query_embedding_fails(monkeypatch):
    def fake_embed(texts, mode, jina_task):
        assert texts == ["agent tools"]
        assert mode == "production"
        assert jina_task == "retrieval.query"
        return [[0.2] * 512], "deepinfra"

    monkeypatch.setattr(rerank_worker, "embed_with_fallback", fake_embed)
    monkeypatch.setattr(
        rerank_worker,
        "qdrant_search",
        lambda **kwargs: [
            {
                "id": "p1",
                "score": 0.7,
                "payload": {
                    "source_type": "paper",
                    "source_id": "paper-1",
                    "title": "Agent benchmark",
                    "source_url": "https://example.com/paper",
                },
            }
        ],
    )
    monkeypatch.setattr(
        rerank_worker,
        "deepinfra_rerank",
        lambda query, documents: [{"index": 0, "score": 0.91}],
    )

    rows = rerank_worker.rerank_theme("agent tools", run_date=date(2026, 4, 28))

    assert rows[0]["source_id"] == "paper-1"
