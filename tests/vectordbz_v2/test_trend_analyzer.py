from datetime import date

from vectordbz_v2 import trend_analyzer


class _Message:
    def __init__(self, content: str):
        self.content = content


class _Choice:
    def __init__(self, content: str):
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str):
        self.choices = [_Choice(content)]
        self.usage = None


class _Completion:
    def __init__(self, content: str, calls: list[dict]):
        self._content = content
        self._calls = calls

    def create(self, **kwargs):
        self._calls.append(kwargs)
        return _Response(self._content)


class _Chat:
    def __init__(self, content: str, calls: list[dict]):
        self.completions = _Completion(content, calls)


class _Client:
    def __init__(self, content: str, calls: list[dict]):
        self.chat = _Chat(content, calls)


class _FailingCompletion:
    def __init__(self, exc: Exception):
        self._exc = exc

    def create(self, **kwargs):
        raise self._exc


class _FailingChat:
    def __init__(self, exc: Exception):
        self.completions = _FailingCompletion(exc)


class _FailingClient:
    def __init__(self, exc: Exception):
        self.chat = _FailingChat(exc)


def test_generate_trend_report_prompts_with_deterministic_contract(monkeypatch):
    calls = []

    monkeypatch.setattr(
        trend_analyzer,
        "get_llm_client",
        lambda provider: (_Client('{"stats": {"total_articles": 1}}', calls), "test-model"),
    )
    monkeypatch.setattr(trend_analyzer.config, "LLM_MAX_RETRIES", 1)

    result = trend_analyzer.generate_trend_report(
        [
            {
                "source_type": "job",
                "sub_source": "AI job market hiring",
                "rank": 1,
                "source_id": "job-1",
                "title": "RAG Platform Engineer",
                "source_url": "https://example.com/rag-platform-engineer",
                "rerank_score": 0.91,
                "llm_summary": "",
            }
        ],
        date(2026, 4, 28),
        source_health={"state": "ok"},
    )

    assert result is not None
    assert "contract" in result["report_json"]
    assert "narrative" in result["report_json"]
    assert result["report_json"]["narrative"] == {"stats": {"total_articles": 1}}
    prompt = calls[0]["messages"][1]["content"]
    assert "Deterministic report contract" in prompt
    assert "job_opportunity_directions" in prompt
    assert "raw ranked rows" not in prompt.lower()


def test_generate_trend_report_returns_none_when_llm_json_is_invalid(monkeypatch):
    monkeypatch.setattr(
        trend_analyzer,
        "get_llm_client",
        lambda provider: (_Client("I cannot produce JSON today.", []), "test-model"),
    )
    monkeypatch.setattr(trend_analyzer.config, "LLM_MAX_RETRIES", 1)

    result = trend_analyzer.generate_trend_report(
        [
            {
                "source_type": "paper",
                "sub_source": "agent eval",
                "rank": 1,
                "source_id": "paper-1",
                "title": "Reliable Agent Evaluation",
                "source_url": "https://arxiv.org/abs/1",
                "rerank_score": 0.8,
                "llm_summary": "",
            }
        ],
        date(2026, 4, 28),
    )

    assert result is None


def test_generate_trend_report_falls_back_provider_immediately_on_rate_limit(monkeypatch):
    calls = []
    providers = []

    class RateLimited(Exception):
        status_code = 429

    def fake_get_llm_client(provider):
        providers.append(provider)
        if provider == "deepinfra":
            return _FailingClient(RateLimited("Too Many Requests")), "deepinfra-model"
        return _Client('{"stats": {"total_articles": 1}}', calls), "openrouter-model"

    monkeypatch.setattr(trend_analyzer, "get_llm_client", fake_get_llm_client)
    monkeypatch.setattr(trend_analyzer.config, "LLM_MAX_RETRIES", 3)
    monkeypatch.setattr(trend_analyzer.time, "sleep", lambda seconds: (_ for _ in ()).throw(AssertionError("rate limit should not sleep")))

    result = trend_analyzer.generate_trend_report(
        [
            {
                "source_type": "paper",
                "sub_source": "agent eval",
                "rank": 1,
                "source_id": "paper-1",
                "title": "Reliable Agent Evaluation",
                "source_url": "https://arxiv.org/abs/1",
                "rerank_score": 0.8,
                "llm_summary": "",
            }
        ],
        date(2026, 4, 28),
    )

    assert result is not None
    assert providers == ["deepinfra", "openrouter"]
    assert result["model_used"] == "openrouter/openrouter-model"


def test_run_trend_analyzer_persists_source_health_when_provided(monkeypatch):
    inserted_reports = []
    inserted_health = []
    source_health = {"state": "ok", "can_publish": True, "warnings": []}

    monkeypatch.setattr(
        trend_analyzer,
        "load_reranked_data",
        lambda run_date: [{"source_type": "job", "source_id": "job-1", "title": "AI Engineer"}],
    )
    monkeypatch.setattr(
        trend_analyzer,
        "generate_trend_report",
        lambda articles, run_date, period_type, source_health=None: {
            "period_type": period_type,
            "period_date": run_date,
            "report_json": {"stats": {"total_articles": 1}},
            "model_used": "test/model",
            "token_cost": 0,
        },
    )
    monkeypatch.setattr(trend_analyzer, "ch_insert_trend_report", inserted_reports.append)
    monkeypatch.setattr(
        trend_analyzer,
        "ch_insert_source_health",
        lambda health, run_date=None: inserted_health.append((health, run_date)),
    )

    report = trend_analyzer.run_trend_analyzer(
        run_date=date(2026, 4, 28),
        period_type="daily",
        source_health=source_health,
    )

    assert report is not None
    assert inserted_reports
    assert inserted_health == [(source_health, date(2026, 4, 28))]


def test_validate_report_payload_requires_contract_and_narrative_schema():
    payload = {
        "contract": {
            "source_counts": {},
            "source_health": {"state": "ok"},
            "top_by_source": {},
            "strongest_signals": [],
            "evidence_signals": [],
            "best_papers": {"top_venue": [], "preprints": []},
            "job_opportunity_directions": [],
        },
        "narrative": {
            "stats": {"total_articles": 0, "sources": {}},
            "core_findings": [],
            "emerging_themes": [],
            "action_items": [],
            "executive_summary": "No high-signal changes.",
        },
    }

    assert trend_analyzer.validate_report_payload(payload) is True


def test_validate_report_payload_rejects_missing_narrative_key():
    assert trend_analyzer.validate_report_payload({"contract": {}}) is False
