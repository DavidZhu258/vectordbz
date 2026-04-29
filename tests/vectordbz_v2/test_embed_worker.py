from vectordbz_v2 import embed_worker


def test_embed_worker_stops_when_provider_failures_reach_max(monkeypatch):
    article = {
        "source_type": "paper",
        "source_id": "paper-1",
        "title": "Reliable agent systems",
        "content": "Testing provider failure handling.",
    }

    monkeypatch.setattr(embed_worker, "ch_get_unembedded", lambda limit: [article] * limit)

    def fail_embedding(texts, mode="production"):
        raise RuntimeError("all providers failed")

    monkeypatch.setattr(embed_worker, "embed_with_fallback", fail_embedding)
    monkeypatch.setattr(embed_worker.time, "sleep", lambda seconds: None)

    embedded, failed = embed_worker.run_embed_worker(
        batch_size=2,
        max_articles=3,
        mode="production",
    )

    assert embedded == 0
    assert failed == 3


def test_embed_worker_caps_last_batch_to_remaining_budget(monkeypatch):
    calls = []
    article = {
        "source_type": "paper",
        "source_id": "paper-1",
        "title": "Reliable agent systems",
        "content": "Testing batch cap.",
    }

    def fake_unembedded(limit):
        calls.append(limit)
        return [article] * limit

    def fake_embedding(texts, mode="production"):
        return [[0.1] * 512 for _ in texts], "test-provider"

    monkeypatch.setattr(embed_worker, "ch_get_unembedded", fake_unembedded)
    monkeypatch.setattr(embed_worker, "embed_with_fallback", fake_embedding)
    monkeypatch.setattr(embed_worker, "qdrant_upsert", lambda points: None)
    monkeypatch.setattr(embed_worker, "ch_mark_embedded", lambda keys, model_name: None)
    monkeypatch.setattr(embed_worker.time, "sleep", lambda seconds: None)

    embedded, failed = embed_worker.run_embed_worker(
        batch_size=2,
        max_articles=3,
        mode="production",
    )

    assert embedded == 3
    assert failed == 0
    assert calls == [2, 1]


def test_embed_worker_preserves_source_evidence_in_qdrant_payload(monkeypatch):
    captured_points = []
    article = {
        "source_type": "github_repo",
        "source_id": "gh-1",
        "title": "owner/repo",
        "content": "Repo content",
        "source_url": "https://github.com/owner/repo",
        "metadata": {"stars": 100},
    }

    monkeypatch.setattr(embed_worker, "ch_get_unembedded", lambda limit: [article])
    monkeypatch.setattr(
        embed_worker,
        "embed_with_fallback",
        lambda texts, mode="production": ([[0.1] * 512], "test-provider"),
    )
    monkeypatch.setattr(embed_worker, "qdrant_upsert", lambda points: captured_points.extend(points))
    monkeypatch.setattr(embed_worker, "ch_mark_embedded", lambda keys, model_name: None)
    monkeypatch.setattr(embed_worker.time, "sleep", lambda seconds: None)

    embed_worker.run_embed_worker(batch_size=1, max_articles=1, mode="production")

    payload = captured_points[0]["payload"]
    assert payload["source_url"] == "https://github.com/owner/repo"
    assert payload["metadata"] == {"stars": 100}
