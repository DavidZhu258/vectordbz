"""
VectorDBZ V2 — Embedding Worker
Embeds unprocessed articles from ClickHouse → Qdrant.

Provider chain:
  1. Jina v3 (production, stable) — with task=retrieval.passage
  2. ChatAnywhere (bulk initial indexing, cheap but unstable)
  3. DeepInfra Qwen3-Embedding (fallback)
"""
import hashlib
import logging
import time
from datetime import datetime, timezone

import requests
from openai import OpenAI

from . import config
from .db import ch_get_unembedded, ch_mark_embedded, qdrant_upsert

logger = logging.getLogger("vectordbz_v2.embed")


def _hash_point_id(source_type: str, source_id: str) -> str:
    """Deterministic Qdrant point ID from source_type:source_id."""
    raw = f"{source_type}:{source_id}"
    return hashlib.md5(raw.encode()).hexdigest()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Embedding Providers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def embed_jina(texts: list[str], task: str = "retrieval.passage") -> list[list[float]]:
    """
    Jina v3 embedding — production primary.
    Supports task-specific embeddings and Matryoshka dimension truncation.
    """
    resp = requests.post(
        config.JINA_EMBEDDING_URL,
        headers={
            "Authorization": f"Bearer {config.JINA_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.JINA_EMBEDDING_MODEL,
            "input": texts,
            "task": task,
            "dimensions": config.EMBEDDING_DIMENSIONS,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return [d["embedding"] for d in data["data"]]


def embed_chatanywhere(texts: list[str]) -> list[list[float]]:
    """
    ChatAnywhere embedding — cheap bulk indexing.
    Uses OpenAI text-embedding-3-small with dimension truncation.
    """
    client = OpenAI(
        base_url=config.CHATANYWHERE_BASE_URL,
        api_key=config.CHATANYWHERE_API_KEY,
    )
    resp = client.embeddings.create(
        model=config.CHATANYWHERE_EMBEDDING_MODEL,
        input=texts,
        dimensions=config.EMBEDDING_DIMENSIONS,
    )
    return [d.embedding for d in resp.data]


def embed_deepinfra(texts: list[str]) -> list[list[float]]:
    """DeepInfra Qwen3-Embedding — stable fallback."""
    client = OpenAI(
        base_url=config.DEEPINFRA_BASE_URL,
        api_key=config.DEEPINFRA_API_KEY,
    )
    resp = client.embeddings.create(
        model=config.DEEPINFRA_EMBEDDING_MODEL,
        input=texts,
        dimensions=config.EMBEDDING_DIMENSIONS,
    )
    return [d.embedding for d in resp.data]


def embed_with_fallback(
    texts: list[str],
    mode: str = "production",
    jina_task: str = "retrieval.passage",
) -> tuple[list[list[float]], str]:
    """
    Embed texts with automatic fallback.
    
    mode="production":  Jina → DeepInfra
    mode="bulk":        ChatAnywhere → DeepInfra → Jina
    
    Returns: (embeddings, provider_name)
    """
    if mode == "bulk":
        providers = [
            ("chatanywhere", embed_chatanywhere),
            ("deepinfra", embed_deepinfra),
            ("jina", lambda t: embed_jina(t, jina_task)),
        ]
    else:
        providers = [
            ("jina", lambda t: embed_jina(t, jina_task)),
            ("deepinfra", embed_deepinfra),
        ]

    for name, fn in providers:
        try:
            result = fn(texts)
            if result and len(result) == len(texts):
                return result, name
        except Exception as e:
            logger.warning(f"Embedding provider {name} failed: {e}")
            continue

    raise RuntimeError(f"All embedding providers failed for {len(texts)} texts!")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main Worker
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def run_embed_worker(
    batch_size: int = 64,
    max_articles: int = 5000,
    mode: str = "production",
):
    """
    Main embedding loop:
    1. Query CH for unembedded articles
    2. Generate embeddings (Jina/ChatAnywhere/DeepInfra)
    3. Upsert to Qdrant
    4. Mark as embedded in CH
    """
    total_embedded = 0
    total_failed = 0

    while total_embedded + total_failed < max_articles:
        remaining = max_articles - total_embedded - total_failed

        # 1. Get unembedded articles
        articles = ch_get_unembedded(limit=min(batch_size, remaining))
        articles = articles[:remaining]
        if not articles:
            logger.info("No more unembedded articles.")
            break

        # 2. Prepare texts for embedding
        texts = []
        for a in articles:
            # Combine title + content for richer embedding
            text = f"{a['title']}\n{a['content']}" if a["content"] else a["title"]
            # Truncate to ~2000 chars to stay within token limits
            texts.append(text[:2000])

        # 3. Generate embeddings
        try:
            embeddings, provider = embed_with_fallback(texts, mode=mode)
        except RuntimeError as e:
            logger.error(f"Embedding completely failed: {e}")
            total_failed += len(articles)
            time.sleep(30)
            continue

        # 4. Prepare Qdrant points
        points = []
        keys = []
        for article, embedding in zip(articles, embeddings):
            point_id = _hash_point_id(article["source_type"], article["source_id"])
            points.append({
                "id": point_id,
                "vector": embedding,
                "payload": {
                    "source_type": article["source_type"],
                    "source_id": article["source_id"],
                    "title": article["title"],
                    "source_url": article.get("source_url", ""),
                    "metadata": article.get("metadata", {}),
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                },
            })
            keys.append((article["source_type"], article["source_id"]))

        # 5. Upsert to Qdrant
        qdrant_upsert(points)

        # 6. Mark as embedded in ClickHouse
        model_name = {
            "jina": config.JINA_EMBEDDING_MODEL,
            "chatanywhere": config.CHATANYWHERE_EMBEDDING_MODEL,
            "deepinfra": config.DEEPINFRA_EMBEDDING_MODEL,
        }.get(provider, provider)
        ch_mark_embedded(keys, model_name)

        total_embedded += len(articles)
        logger.info(
            f"Progress: {total_embedded}/{max_articles} embedded "
            f"(provider={provider}, batch={len(articles)})"
        )

        # Rate limit respect
        time.sleep(0.5)

    logger.info(
        f"Embedding complete: {total_embedded} embedded, {total_failed} failed"
    )
    return total_embedded, total_failed


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="VectorDBZ V2 Embed Worker")
    parser.add_argument("--mode", choices=["production", "bulk"], default="production",
                        help="production=Jina first, bulk=ChatAnywhere first")
    parser.add_argument("--max", type=int, default=5000, help="Max articles to embed")
    parser.add_argument("--batch", type=int, default=64, help="Batch size")
    args = parser.parse_args()

    embedded, failed = run_embed_worker(
        batch_size=args.batch,
        max_articles=args.max,
        mode=args.mode,
    )
    sys.exit(0 if failed == 0 else 1)
