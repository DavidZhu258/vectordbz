from fastapi.testclient import TestClient

from vectordbz_v2.api import app


def test_v2_api_health_is_local_and_external_ready():
    client = TestClient(app)

    response = client.get("/api/v2/health")

    assert response.status_code == 200
    assert response.json()["service"] == "vectordbz_v2"
    assert response.json()["state"] == "ok"
    assert response.json()["external_bind_host"] == "0.0.0.0"


def test_v2_api_ask_returns_cited_payload_from_supplied_signals():
    client = TestClient(app)

    response = client.post(
        "/api/v2/ask",
        json={
            "query": "Why avoid heavy agent frameworks?",
            "signals": [
                {
                    "source_type": "reddit",
                    "source_id": "rd-1",
                    "title": "Heavy frameworks add latency",
                    "source_url": "https://reddit.com/r/LocalLLaMA/comments/rd-1",
                    "evidence": ["Tool-call latency and recovery matter in production."],
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer_state"] == "answerable"
    assert body["citations"] == ["reddit:rd-1:1"]
