"""Initialize VectorDBZ V2 ClickHouse tables and Qdrant collection."""

from __future__ import annotations

import json
import logging

from .db import ensure_runtime_schema


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    result = ensure_runtime_schema()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
