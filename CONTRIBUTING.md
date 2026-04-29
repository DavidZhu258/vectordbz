# Contributing to VectorDBZ

VectorDBZ v2.0 is a compact AI information aggregation platform. Contributions
should make the system more precise, more maintainable, or easier to operate on
independent servers.

## Good Contributions

- Better source connectors with clear quality rules.
- Stronger evidence extraction and citation payloads.
- Faster or cheaper embedding, rerank, and report phases.
- More reliable checkpointing, health checks, and server deployment.
- Focused UI reuse for Source Health, Daily Signals, Evidence Drawer, Ask With
  Citations, and Runner Status.
- Documentation that reduces operational ambiguity.

## Development Flow

```bash
git clone https://github.com/DavidZhu258/vectordbz.git
cd vectordbz
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r deploy/vectordbz_v2/requirements.txt pytest
python -m pytest tests/vectordbz_v2 -q
```

On Windows PowerShell, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

## Pull Request Checklist

- Tests pass: `python -m pytest tests\vectordbz_v2 -q`.
- `git diff --check` has no whitespace errors.
- No secrets, `.env` files, local archives, caches, screenshots, vector stores,
  or `node_modules` are committed.
- New source connectors have source health behavior and tests.
- LLM-facing changes preserve deterministic contracts before narration.
- Server behavior is controlled through environment variables, not hardcoded
  local paths.

## Reporting Bugs

Use GitHub issues for normal bugs. Include:

- the command or endpoint used,
- expected behavior,
- actual behavior,
- relevant non-secret logs,
- whether ClickHouse/Qdrant/provider credentials were configured.

For security vulnerabilities, follow `SECURITY.md` and do not open a public
issue.
