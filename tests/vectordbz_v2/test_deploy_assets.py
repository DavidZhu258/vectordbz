from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_deploy_assets_bind_api_externally_without_committed_secrets():
    service = (ROOT / "deploy" / "vectordbz_v2" / "vectordbz-v2-api.service").read_text()
    env_153 = (ROOT / "profiles" / "153.env.example").read_text()
    env_us = (ROOT / "profiles" / "us.env.example").read_text()

    assert "--host 0.0.0.0" in service
    assert "VDBZ_API_PORT=4636" in env_153
    assert "VDBZ_API_PORT=4640" in env_us
    for env_text in [env_153, env_us]:
        for key in [
            "JINA_API_KEY",
            "DEEPINFRA_API_KEY",
            "OPENROUTER_API_KEY",
            "GITHUB_TOKEN",
            "CLICKHOUSE_PASSWORD",
            "QDRANT_API_KEY",
        ]:
            assert f"{key}=" in env_text
            assert f"{key}=replace" not in env_text


def test_deploy_readme_documents_local_gates_before_server_deploy():
    readme = (ROOT / "deploy" / "vectordbz_v2" / "README.md").read_text()
    requirements = (ROOT / "deploy" / "vectordbz_v2" / "requirements.txt").read_text()

    assert "python -m pytest tests\\vectordbz_v2 -q" in readme
    assert "python -m vectordbz_v2.init_schema" in readme
    assert "python -m vectordbz_v2.test_smoke" in readme
    assert "clean git ref" in readme
    assert "fastapi" in requirements
    assert "clickhouse-connect" in requirements
    assert "qdrant-client" in requirements


def test_v2_runtime_files_do_not_reference_local_windows_project_path():
    runtime_files = list((ROOT / "vectordbz_v2").glob("*.py"))

    offenders = [
        path.name
        for path in runtime_files
        if "e:\\python_project\\vectordbz" in path.read_text(encoding="utf-8").lower()
    ]

    assert offenders == []
