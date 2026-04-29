"""
VectorDBZ V2 — Rerank Worker
Retrieves candidates from Qdrant, reranks via DeepInfra API, writes to ClickHouse.

Flow:
  1. Build theme queries (from recent trend keywords or static topics)
  2. Qdrant cosine search → top-50 candidates per query
  3. DeepInfra Qwen3-Reranker → score and reorder
  4. Write top-20 per source_type to analytics_v2.rerank_cache
"""
import logging
import time
from datetime import date, datetime, timezone

import requests

from . import config
from .db import ch_insert_rerank, qdrant_search
from .embed_worker import embed_with_fallback

logger = logging.getLogger("vectordbz_v2.rerank")

# Default research themes for daily reranking
DEFAULT_THEMES = [
    "Large language model agent framework tool use",
    "AI alignment safety reinforcement learning from human feedback",
    "Multimodal vision language model benchmark",
    "RAG retrieval augmented generation vector database production",
    "Diffusion model image video generation",
    "AI coding assistant software engineering automation",
    "Open source model fine-tuning LoRA QLoRA quantization",
    "AI job market hiring machine learning engineer",
    "Hugging Face trending model dataset",
    "AI startup funding investment venture capital",
]


def deepinfra_rerank(
    query: str,
    documents: list[str],
    model: str = None,
) -> list[dict]:
    """
    Call DeepInfra Qwen3-Reranker API.
    Returns list of {"index": int, "score": float} sorted by score desc.
    """
    model = model or config.DEEPINFRA_RERANKER_MODEL
    url = f"https://api.deepinfra.com/v1/inference/{model}"

    for attempt in range(config.LLM_MAX_RETRIES):
        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"bearer {config.DEEPINFRA_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "queries": [query],
                    "documents": documents,
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()

            # Parse scores — API returns {"scores": [...]} or {"results": [...]}
            scores = data.get("scores", [])
            if not scores and "results" in data:
                scores = [r.get("relevance_score", 0) for r in data["results"]]

            results = [
                {"index": i, "score": s}
                for i, s in enumerate(scores)
            ]
            results.sort(key=lambda x: x["score"], reverse=True)
            return results

        except Exception as e:
            logger.warning(f"Rerank attempt {attempt+1} failed ({model}): {e}")
            if attempt < config.LLM_MAX_RETRIES - 1:
                time.sleep(config.LLM_RETRY_DELAY)
            else:
                # Try fallback model
                if model != config.DEEPINFRA_RERANKER_FALLBACK:
                    logger.info(f"Falling back to {config.DEEPINFRA_RERANKER_FALLBACK}")
                    return deepinfra_rerank(
                        query, documents,
                        model=config.DEEPINFRA_RERANKER_FALLBACK,
                    )
                raise


def rerank_theme(
    theme: str,
    source_types: list[str] | None = None,
    days: int = 7,
    run_date: date | None = None,
) -> list[dict]:
    """
    Rerank articles for a single theme:
    1. Embed the theme query with Jina (task=retrieval.query)
    2. Search Qdrant for top candidates
    3. Rerank with DeepInfra
    4. Return scored results
    """
    run_date = run_date or date.today()

    # 1. Embed the query
    try:
        query_vectors, _provider = embed_with_fallback(
            [theme],
            mode="production",
            jina_task="retrieval.query",
        )
        query_vec = query_vectors[0]
    except Exception as e:
        logger.error(f"Query embedding failed for '{theme}': {e}")
        return []

    # 2. Qdrant search
    candidates = qdrant_search(
        query_vector=query_vec,
        source_types=source_types,
        days=days,
        limit=config.RERANK_TOP_K,
    )

    if not candidates:
        logger.warning(f"No candidates found for theme: {theme}")
        return []

    # 3. Prepare documents for reranking
    docs = [
        f"{c['payload'].get('title', '')} — {c['payload'].get('source_type', '')}"
        for c in candidates
    ]

    # 4. Rerank
    try:
        ranked = deepinfra_rerank(query=theme, documents=docs)
    except Exception as e:
        logger.error(f"Reranking failed for theme '{theme}': {e}")
        return []

    # 5. Build results
    results = []
    for rank_idx, r in enumerate(ranked[: config.RERANK_FINAL_K]):
        orig = candidates[r["index"]]
        results.append({
            "run_date": run_date,
            "source_type": orig["payload"].get("source_type", ""),
            "sub_source": theme[:50],
            "rank": rank_idx + 1,
            "source_id": orig["payload"].get("source_id", ""),
            "title": orig["payload"].get("title", ""),
            "source_url": orig["payload"].get("source_url", ""),
            "rerank_score": r["score"],
            "llm_summary": "",
            "model_used": config.DEEPINFRA_RERANKER_MODEL,
        })

    return results


def run_rerank_worker(
    themes: list[str] | None = None,
    source_types: list[str] | None = None,
    days: int = 7,
    run_date: date | None = None,
):
    """
    Main reranking loop: iterate themes, rerank for each, write to CH.
    """
    themes = themes or DEFAULT_THEMES
    run_date = run_date or date.today()
    total_results = 0

    for theme in themes:
        logger.info(f"Reranking theme: {theme[:60]}...")
        results = rerank_theme(
            theme=theme,
            source_types=source_types,
            days=days,
            run_date=run_date,
        )

        if results:
            ch_insert_rerank(results)
            total_results += len(results)

        time.sleep(1)  # Rate limit

    logger.info(f"Reranking complete: {total_results} results for {len(themes)} themes")
    return total_results


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="VectorDBZ V2 Rerank Worker")
    parser.add_argument("--days", type=int, default=7, help="Look back N days")
    parser.add_argument("--date", type=str, default=None, help="Run date (YYYY-MM-DD)")
    args = parser.parse_args()

    rd = date.fromisoformat(args.date) if args.date else date.today()
    run_rerank_worker(days=args.days, run_date=rd)
