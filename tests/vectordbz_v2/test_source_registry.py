from vectordbz_v2.source_registry import (
    DEFAULT_REDDIT_SUBREDDITS,
    annotate_article_with_source_rule,
    default_source_registry,
    evaluate_reddit_candidate,
)


def test_default_reddit_registry_is_small_and_purposeful():
    registry = default_source_registry()

    assert DEFAULT_REDDIT_SUBREDDITS == [
        "LocalLLaMA",
        "AI_Agents",
        "MachineLearning",
        "LLMDevs",
        "artificial",
        "SaaS",
        "startups",
        "ProductManagement",
        "datascience",
        "datasets",
        "MLQuestions",
    ]
    assert set(DEFAULT_REDDIT_SUBREDDITS) <= set(registry)
    assert registry["LocalLLaMA"].purpose == "local LLM deployment, cost, model, and agent operations"
    assert registry["SaaS"].category == "product_market"
    assert registry["MachineLearning"].min_score >= 50


def test_reddit_candidate_evaluation_explains_accept_and_reject():
    accepted = evaluate_reddit_candidate({
        "metadata": {"subreddit": "LocalLLaMA", "score": 220, "num_comments": 44},
        "title": "How are people keeping long-running local agents alive?",
        "content": "State persistence and tool latency are the main production issues.",
    })

    rejected = evaluate_reddit_candidate({
        "metadata": {"subreddit": "LocalLLaMA", "score": 3, "num_comments": 0},
        "title": "My AI newsletter giveaway",
        "content": "Buy now for free credits.",
    })

    assert accepted["accepted"] is True
    assert accepted["reason"] == "meets LocalLLaMA thresholds: score>=100, comments>=20"
    assert rejected["accepted"] is False
    assert rejected["reason"] == "excluded promotional or low-signal wording"


def test_annotate_article_with_source_rule_adds_selection_metadata_without_secrets():
    article = {
        "source_type": "reddit",
        "source_id": "rd-1",
        "title": "Agent framework production failure modes",
        "content": "Tool retries and observability matter.",
        "metadata": {"subreddit": "AI_Agents", "score": 80, "num_comments": 14},
    }

    annotated = annotate_article_with_source_rule(article)

    assert annotated["metadata"]["source_rule"] == "AI_Agents"
    assert annotated["metadata"]["source_rule_category"] == "ai_agent"
    assert annotated["metadata"]["selection_reason"] == "meets AI_Agents thresholds: score>=30, comments>=5"
    assert "password" not in str(annotated["metadata"]).lower()
