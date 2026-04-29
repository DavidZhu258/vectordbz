"""Smoke test: verify ClickHouse analytics_v2 + Qdrant articles_v2 are ready."""

from vectordbz_v2.db import get_ch, qdrant_collection_info

def main():
    print("=== ClickHouse analytics_v2 ===")
    ch = get_ch()
    tables = ch.query("SHOW TABLES").result_rows
    for t in tables:
        cnt = ch.query(f"SELECT count() FROM {t[0]}").result_rows[0][0]
        print(f"  {t[0]}: {cnt} rows")

    print("\n=== Qdrant articles_v2 ===")
    info = qdrant_collection_info()
    print(f"  status: {info['status']}")
    print(f"  vectors: {info['points_count']}")
    vec_cfg = info["config"]["params"]["vectors"]
    print(f"  dim: {vec_cfg['size']}, distance: {vec_cfg['distance']}")
    sq = info["config"]["quantization_config"]["scalar"]
    print(f"  SQ: type={sq['type']}, quantile={sq['quantile']}, always_ram={sq['always_ram']}")
    hnsw = info["config"]["hnsw_config"]
    print(f"  HNSW: m={hnsw['m']}, ef_construct={hnsw['ef_construct']}")
    print(f"  payload indexes: {list(info['payload_schema'].keys())}")

    print("\n=== ALL SYSTEMS GO ===")

if __name__ == "__main__":
    main()
