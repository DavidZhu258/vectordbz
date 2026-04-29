from vectordbz_v2.service_registry import (
    ARTICLE_SOURCE_TYPES,
    UPSTREAM_SERVICES,
    service_names,
    validate_article_source_coverage,
)


def test_upstream_registry_contains_all_153_dag_services_and_local_live_sources():
    expected = {
        "crawl",
        "jobspy",
        "ever_jobs",
        "foorilla",
        "news_rss",
        "pyalex",
        "reddit_discovery",
        "finance",
        "health_report",
        "github_hf_live",
    }

    assert expected <= set(service_names(UPSTREAM_SERVICES))


def test_article_source_coverage_matches_v2_source_types():
    assert ARTICLE_SOURCE_TYPES == {
        "paper",
        "news",
        "reddit",
        "job",
        "github_repo",
        "hf_model",
        "hf_dataset",
        "hf_space",
    }
    assert validate_article_source_coverage(ARTICLE_SOURCE_TYPES) == []
    assert validate_article_source_coverage({"paper", "news"}) == [
        "github_repo",
        "hf_dataset",
        "hf_model",
        "hf_space",
        "job",
        "reddit",
    ]
