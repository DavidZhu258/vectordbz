"""
VectorDBZ V2 — Unified Configuration
All providers, DB connections, and constants in one place.
"""
import os

# ──────────────────────────────────────────────────────────────────
# Embedding Providers (Jina primary, ChatAnywhere bulk, DeepInfra fallback)
# ──────────────────────────────────────────────────────────────────
JINA_API_KEY = os.getenv("JINA_API_KEY", "")
JINA_EMBEDDING_MODEL = "jina-embeddings-v3"
JINA_EMBEDDING_URL = "https://api.jina.ai/v1/embeddings"

CHATANYWHERE_API_KEY = os.getenv("CHATANYWHERE_API_KEY", "")
CHATANYWHERE_BASE_URL = "https://api.chatanywhere.tech/v1"
CHATANYWHERE_EMBEDDING_MODEL = "text-embedding-3-small"

DEEPINFRA_API_KEY = os.getenv("DEEPINFRA_API_KEY", "")
DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"
DEEPINFRA_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"

EMBEDDING_DIMENSIONS = 512  # Matryoshka sweet spot

# ──────────────────────────────────────────────────────────────────
# Reranker (DeepInfra)
# ──────────────────────────────────────────────────────────────────
DEEPINFRA_RERANKER_MODEL = "Qwen/Qwen3-Reranker-0.6B"
DEEPINFRA_RERANKER_URL = "https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-0.6B"
DEEPINFRA_RERANKER_FALLBACK = "Qwen/Qwen3-Reranker-4B"

# ──────────────────────────────────────────────────────────────────
# LLM (DeepInfra → OpenRouter fallback)
# ──────────────────────────────────────────────────────────────────
DEEPINFRA_LLM_MODEL = "Qwen/Qwen3-235B-A22B"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_LLM_MODEL = "qwen/qwen3-30b-a3b"

# ──────────────────────────────────────────────────────────────────
# ClickHouse (analytics_v2)
# ──────────────────────────────────────────────────────────────────
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "9000"))
CLICKHOUSE_HTTP_PORT = int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))
CLICKHOUSE_DB = "analytics_v2"
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")

# V1 database (read-only for migration)
CLICKHOUSE_V1_DB = "analytics"

# ──────────────────────────────────────────────────────────────────
# Qdrant
# ──────────────────────────────────────────────────────────────────
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_GRPC_PORT = int(os.getenv("QDRANT_GRPC_PORT", "6334"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_COLLECTION = "articles_v2"

# ──────────────────────────────────────────────────────────────────
# Data Sources
# ──────────────────────────────────────────────────────────────────
SOURCE_TYPES = ["paper", "news", "reddit", "job", "hf_trending"]

EMBEDDING_BATCH_SIZE = 64   # Jina batch limit
RERANK_TOP_K = 50           # Qdrant recall count
RERANK_FINAL_K = 20         # Final reranked count per source
LLM_MAX_RETRIES = 3
LLM_RETRY_DELAY = 30        # seconds

# ──────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.getenv("LOG_DIR", "/opt/vectordbz_v2/logs")
