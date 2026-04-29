# VectorDBZ v2.0 Harness Execution Plan

> Updated: 2026-04-28

## Goal

Complete the minimal v2.0 harness locally, verify it, then deploy a clean git ref to the 153 crawler server and US server with externally reachable dashboard/API ports.

## Scope

Edit only scoped v2 files:

- `vectordbz_v2/`
- `tests/vectordbz_v2/`
- `docs/`
- `profiles/`
- `deploy/vectordbz_v2/`

Do not modify unrelated v1/dashboard/application files unless a later UI integration task explicitly requires it.

## Execution Order

1. Add source registry rules for selected Reddit and intelligence sources.
2. Add Elicit-style evidence schema and deterministic cited Q&A payloads.
3. Add resumable long-task checkpoint support.
4. Add Linux deployment assets with environment-only secrets and port exposure notes.
5. Run local verification gates.
6. Create a clean scoped commit/ref.
7. Deploy to 153 and US servers from that clean ref.
8. Verify service health and external access.

## Local Gates

- `python -m pytest tests\vectordbz_v2 -q`
- `python -m vectordbz_v2.test_smoke`
- `python -m vectordbz_v2.collector_health --limit 1`
- `python -m vectordbz_v2.source_backfill --start 2026-04-01 --end 2026-04-28 --per-day-limit 20 --dry-run`
- bounded `python -m vectordbz_v2.long_task_runner ...`
- token/secret scan over scoped files

## Deployment Gates

Deployment is blocked until local gates pass and the deploy artifact is a clean git ref. Server secrets must be set in environment files or systemd drop-ins on the server, never committed.

The deployment targets are:

- 153 crawler server from the local server inventory.
- US server from the local server inventory.

HK remains a diagnostic/dashboard reference, not the primary target for this user request.
