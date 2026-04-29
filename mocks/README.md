# Legacy v1 Mock Data

This directory is retained for the v1 UI/application baseline. It contains Node
seed scripts that populate local vector database fixtures used by the historical
desktop client tests.

VectorDBZ v2.0 does not use these fixtures for the evidence-first information
pipeline. The v2 runtime lives under `vectordbz_v2/` and writes to ClickHouse
`analytics_v2` plus Qdrant `articles_v2`.

## When to Use This Directory

Use these scripts only when working on the legacy v1 UI/database explorer code
under `app/`.

```bash
cd mocks
npm install
npm run seed
npm run clean
```

For v2 development, use:

```powershell
python -m pytest tests\vectordbz_v2 -q
python -m vectordbz_v2.init_schema
python -m vectordbz_v2.test_smoke
```

## Secret Rule

Do not commit real `.env` files or cloud database keys for these legacy seed
scripts. Keep any local values outside git.
