"""
End-to-end test: migrate 10 papers → embed with Jina → upsert to Qdrant.
"""
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from vectordbz_v2.migrate import migrate_papers
from vectordbz_v2.embed_worker import run_embed_worker
from vectordbz_v2.db import get_ch, qdrant_collection_info

def main():
    # 1. Migrate 10 papers from V1
    print("\n=== STEP 1: Migrate 10 papers from V1 → V2 ===")
    count = migrate_papers(limit=10)
    print(f"Migrated {count} papers")

    # Verify in CH
    ch = get_ch()
    cnt = ch.query("SELECT count() FROM articles").result_rows[0][0]
    print(f"CH articles count: {cnt}")

    # 2. Embed with Jina (production mode)
    print("\n=== STEP 2: Embed with Jina v3 → Qdrant ===")
    embedded, failed = run_embed_worker(batch_size=10, max_articles=10, mode="production")
    print(f"Embedded: {embedded}, Failed: {failed}")

    # 3. Verify Qdrant
    print("\n=== STEP 3: Verify Qdrant ===")
    info = qdrant_collection_info()
    print(f"Qdrant vectors: {info['points_count']}")

    # 4. Test search
    if info["points_count"] > 0:
        print("\n=== STEP 4: Test semantic search ===")
        from vectordbz_v2.embed_worker import embed_jina
        from vectordbz_v2.db import qdrant_search
        
        q_vec = embed_jina(["large language model agent"], task="retrieval.query")[0]
        results = qdrant_search(query_vector=q_vec, days=0, limit=5)
        for r in results:
            print(f"  score={r['score']:.4f} | {r['payload'].get('title', 'N/A')[:80]}")

    print("\n=== E2E TEST COMPLETE ===")

if __name__ == "__main__":
    main()
