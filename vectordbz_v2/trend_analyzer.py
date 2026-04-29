"""
VectorDBZ V2 — Trend Analyzer
Reads reranked data, generates trend reports via DeepInfra LLM, saves to ClickHouse.

Flow:
  1. Read today's rerank_cache from ClickHouse
  2. Group by source_type / sub_source
  3. Send to DeepInfra LLM for analysis
  4. Save structured JSON report to trend_reports
"""
import json
import logging
import time
from datetime import date, datetime, timezone

from openai import OpenAI

from . import config
from .db import get_ch, ch_insert_source_health, ch_insert_trend_report
from .llm_json import parse_llm_json
from .report_contract import build_report_contract
from .source_taxonomy import SOURCE_ORDER, canonical_category, paper_tier, parse_metadata

logger = logging.getLogger("vectordbz_v2.trend")

CONTRACT_KEYS = {
    "source_counts",
    "source_health",
    "top_by_source",
    "strongest_signals",
    "evidence_signals",
    "best_papers",
    "job_opportunity_directions",
}
NARRATIVE_KEYS = {
    "stats",
    "core_findings",
    "emerging_themes",
    "action_items",
    "executive_summary",
}

TREND_SYSTEM_PROMPT = """You are VectorDBZ, an AI research trend analyst.
Analyze the following deterministic report contract and produce a structured JSON report.

Output MUST be valid JSON with this structure:
{
  "stats": {"total_articles": N, "sources": {"paper": N, "news": N, ...}},
  "core_findings": [
    {"title": "...", "summary": "...", "impact": "high|medium|low", "sources": ["source_id1", ...]}
  ],
  "emerging_themes": ["theme1", "theme2", ...],
  "action_items": [
    {"action": "...", "urgency": "high|medium|low", "rationale": "..."}
  ],
  "executive_summary": "2-3 sentence overview of the day's most important developments"
}

Rules:
- Treat the deterministic report contract as the source of truth.
- Do not re-rank raw feeds.
- Cross-reference only the capped source signals present in the contract.
- Preserve negative market signals such as no recent jobs.
"""


def get_llm_client(provider: str = "deepinfra") -> tuple[OpenAI, str]:
    """Get LLM client with provider selection."""
    if provider == "deepinfra":
        return OpenAI(
            base_url=config.DEEPINFRA_BASE_URL,
            api_key=config.DEEPINFRA_API_KEY,
        ), config.DEEPINFRA_LLM_MODEL
    else:
        return OpenAI(
            base_url=config.OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY,
        ), config.OPENROUTER_LLM_MODEL


def load_reranked_data(run_date: date) -> list[dict]:
    """Load reranked articles for a given date from ClickHouse."""
    ch = get_ch()
    result = ch.query(
        f"SELECT source_type, sub_source, rank, source_id, title, "
        f"source_url, rerank_score, llm_summary "
        f"FROM rerank_cache FINAL "
        f"WHERE run_date = '{run_date}' "
        f"ORDER BY source_type, sub_source, rank "
        f"LIMIT 500"
    )

    return [
        {
            "source_type": row[0],
            "sub_source": row[1],
            "rank": row[2],
            "source_id": row[3],
            "title": row[4],
            "source_url": row[5],
            "rerank_score": row[6],
            "llm_summary": row[7],
        }
        for row in result.result_rows
    ]


def build_reranked_signal_digest(
    articles: list[dict],
    per_source_limit: int = 5,
    global_limit: int = 10,
) -> dict:
    """Build a contract-ready digest from already-reranked rows."""
    buckets: dict[str, list[dict]] = {}
    for article in articles:
        signal = _reranked_row_to_signal(article)
        if signal:
            buckets.setdefault(signal["category"], []).append(signal)

    top_by_source: dict[str, list[dict]] = {}
    for category in _ordered_digest_categories(buckets):
        ranked = sorted(buckets[category], key=lambda item: item["score"], reverse=True)
        top_by_source[category] = ranked[:per_source_limit]

    return {
        "source_counts": {category: len(items) for category, items in buckets.items()},
        "top_by_source": top_by_source,
        "strongest_signals": _interleave_digest_signals(top_by_source, global_limit),
    }


def _reranked_row_to_signal(article: dict) -> dict | None:
    source_id = str(article.get("source_id") or "").strip()
    title = str(article.get("title") or "").strip()
    if not source_id or not title:
        return None

    metadata = parse_metadata(article.get("metadata"))
    source_type = str(article.get("source_type") or "").lower()
    category = source_type if source_type in {*SOURCE_ORDER, "paper_candidate"} else canonical_category({
        "source_type": source_type,
        "metadata": metadata,
    })
    tier = str(article.get("tier") or "")
    if not tier and category.startswith("paper_"):
        tier = paper_tier(metadata)

    score = float(article.get("rerank_score") or article.get("score") or 0.0)
    theme = str(article.get("sub_source") or "")
    evidence = [f"rerank_score={score:.3f}"]
    if theme:
        evidence.append(f"theme={theme}")
    if article.get("llm_summary"):
        evidence.append(str(article["llm_summary"])[:180])

    return {
        "category": category,
        "source_type": str(article.get("source_type") or ""),
        "source_id": source_id,
        "title": title,
        "score": round(score, 3),
        "source_url": str(article.get("source_url") or ""),
        "tier": tier,
        "evidence": evidence,
        "metadata": metadata,
    }


def _ordered_digest_categories(buckets: dict[str, list[dict]]) -> list[str]:
    known = [category for category in SOURCE_ORDER if category in buckets]
    unknown = sorted(category for category in buckets if category not in SOURCE_ORDER)
    return known + unknown


def _interleave_digest_signals(
    top_by_source: dict[str, list[dict]],
    global_limit: int,
) -> list[dict]:
    selected: list[dict] = []
    categories = list(top_by_source)
    rank = 0
    while len(selected) < global_limit:
        added = False
        for category in categories:
            items = top_by_source[category]
            if rank < len(items):
                selected.append(items[rank])
                added = True
                if len(selected) >= global_limit:
                    break
        if not added:
            break
        rank += 1
    return selected


def generate_trend_report(
    articles: list[dict],
    run_date: date,
    period_type: str = "daily",
    source_health: dict | None = None,
) -> dict | None:
    """
    Generate a trend report from reranked articles using DeepInfra LLM.
    Includes retry + fallback to OpenRouter.
    """
    if not articles:
        logger.warning(f"No articles for {run_date}, skipping report generation.")
        return None

    digest = build_reranked_signal_digest(articles)
    report_contract = build_report_contract(digest, source_health=source_health)
    contract_text = json.dumps(report_contract, ensure_ascii=False, indent=2, default=str)

    user_prompt = (
        f"Date: {run_date}\n"
        f"Period: {period_type}\n"
        f"Total reranked rows represented: {len(articles)}\n\n"
        f"Deterministic report contract:\n{contract_text}\n\n"
        f"Generate the trend analysis report in JSON format using only this contract."
    )

    # Try DeepInfra first, then OpenRouter
    providers = ["deepinfra", "openrouter"]

    for provider in providers:
        client, model = get_llm_client(provider)
        rate_limited = False

        for attempt in range(config.LLM_MAX_RETRIES):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": TREND_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=4000,
                )

                content = response.choices[0].message.content.strip()

                report_json = parse_llm_json(content)

                # Calculate token cost
                usage = response.usage
                token_cost = (usage.prompt_tokens + usage.completion_tokens) if usage else 0

                logger.info(
                    f"Report generated via {provider}/{model} "
                    f"(tokens={token_cost})"
                )

                return {
                    "period_type": period_type,
                    "period_date": run_date,
                    "report_json": {
                        "contract": report_contract,
                        "narrative": report_json,
                    },
                    "model_used": f"{provider}/{model}",
                    "token_cost": token_cost,
                }

            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"JSON parse error on attempt {attempt+1}: {e}")
            except Exception as e:
                logger.warning(f"LLM call failed ({provider}, attempt {attempt+1}): {e}")
                if _is_rate_limit_error(e):
                    logger.warning(f"Provider rate limited ({provider}); trying next provider.")
                    rate_limited = True
                    break

            if attempt < config.LLM_MAX_RETRIES - 1:
                time.sleep(config.LLM_RETRY_DELAY)

        if not rate_limited:
            logger.warning(f"All retries exhausted for {provider}, trying next...")

    logger.error(f"All LLM providers failed for report {run_date}")
    return None


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    text = str(exc).lower()
    return "429" in text or "too many requests" in text or "rate limit" in text


def validate_report_payload(payload: dict) -> bool:
    """Validate the persisted report envelope shape."""
    if not isinstance(payload, dict):
        return False
    contract = payload.get("contract")
    narrative = payload.get("narrative")
    if not isinstance(contract, dict) or not isinstance(narrative, dict):
        return False
    if not CONTRACT_KEYS <= set(contract):
        return False
    if not NARRATIVE_KEYS <= set(narrative):
        return False
    best_papers = contract.get("best_papers")
    if not isinstance(best_papers, dict):
        return False
    return {"top_venue", "preprints"} <= set(best_papers)


def run_trend_analyzer(
    run_date: date | None = None,
    period_type: str = "daily",
    source_health: dict | None = None,
):
    """
    Main trend analysis pipeline:
    1. Load reranked data
    2. Generate LLM report
    3. Save to ClickHouse
    """
    run_date = run_date or date.today()

    logger.info(f"Starting trend analysis for {period_type} {run_date}...")

    # 1. Load reranked data
    articles = load_reranked_data(run_date)
    if not articles:
        logger.warning(f"No reranked data for {run_date}. Run rerank_worker first.")
        return None

    logger.info(f"Loaded {len(articles)} reranked articles")

    # 2. Generate report
    report = generate_trend_report(articles, run_date, period_type, source_health=source_health)
    if not report:
        logger.error("Report generation failed.")
        return None

    # 3. Save to ClickHouse
    ch_insert_trend_report(report)
    if source_health:
        ch_insert_source_health(source_health, run_date=run_date)

    logger.info(f"Trend report saved: {period_type} {run_date}")
    return report


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="VectorDBZ V2 Trend Analyzer")
    parser.add_argument("--date", type=str, default=None, help="Report date (YYYY-MM-DD)")
    parser.add_argument("--period", choices=["daily", "weekly", "monthly"], default="daily")
    args = parser.parse_args()

    rd = date.fromisoformat(args.date) if args.date else date.today()
    run_trend_analyzer(run_date=rd, period_type=args.period)
