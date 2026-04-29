import importlib


def test_external_provider_api_keys_default_to_empty(monkeypatch):
    for name in [
        "JINA_API_KEY",
        "CHATANYWHERE_API_KEY",
        "DEEPINFRA_API_KEY",
        "OPENROUTER_API_KEY",
    ]:
        monkeypatch.delenv(name, raising=False)

    import vectordbz_v2.config as config

    reloaded = importlib.reload(config)

    assert reloaded.JINA_API_KEY == ""
    assert reloaded.CHATANYWHERE_API_KEY == ""
    assert reloaded.DEEPINFRA_API_KEY == ""
    assert reloaded.OPENROUTER_API_KEY == ""


def test_database_password_defaults_to_empty(monkeypatch):
    monkeypatch.delenv("CLICKHOUSE_PASSWORD", raising=False)

    import vectordbz_v2.config as config

    reloaded = importlib.reload(config)

    assert reloaded.CLICKHOUSE_PASSWORD == ""
