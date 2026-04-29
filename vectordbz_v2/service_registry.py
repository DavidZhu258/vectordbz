"""V2 service inventory for upstream crawlers and local pipeline phases."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceDefinition:
    name: str
    kind: str
    schedule: str
    owner_path: str
    output_tables: tuple[str, ...]
    article_source_types: tuple[str, ...] = ()
    critical: bool = False
    notes: str = ""


UPSTREAM_SERVICES = [
    ServiceDefinition(
        name="crawl",
        kind="153_dagu",
        schedule="*/30 * * * *",
        owner_path="/root/python_project/dags/crawl.yaml",
        output_tables=("analytics.jobs",),
        article_source_types=("job",),
        critical=True,
        notes="Recruiting list-page crawler.",
    ),
    ServiceDefinition(
        name="jobspy",
        kind="153_dagu",
        schedule="0 * * * *",
        owner_path="/root/python_project/dags/jobspy.yaml",
        output_tables=("analytics.jobs",),
        article_source_types=("job",),
        critical=True,
        notes="JobSpy multi-site aggregation.",
    ),
    ServiceDefinition(
        name="ever_jobs",
        kind="153_dagu",
        schedule="0 2 * * *",
        owner_path="/root/python_project/dags/ever_jobs.yaml",
        output_tables=("analytics.jobs",),
        article_source_types=("job",),
        critical=True,
        notes="EverJobs recurring job collection.",
    ),
    ServiceDefinition(
        name="foorilla",
        kind="153_dagu",
        schedule="0 6,18 * * *",
        owner_path="/root/python_project/dags/foorilla.yaml",
        output_tables=("analytics.jobs", "analytics.news"),
        article_source_types=("job", "news"),
        critical=False,
        notes="Foorilla jobs/media/events collector.",
    ),
    ServiceDefinition(
        name="news_rss",
        kind="153_dagu",
        schedule="0 1,7,13,19 * * *",
        owner_path="/root/python_project/dags/news_rss.yaml",
        output_tables=("analytics.news",),
        article_source_types=("news",),
        critical=False,
        notes="RSS news ingestion.",
    ),
    ServiceDefinition(
        name="pyalex",
        kind="153_dagu",
        schedule="0 10 * * *",
        owner_path="/root/python_project/dags/pyalex.yaml",
        output_tables=("analytics.papers",),
        article_source_types=("paper",),
        critical=False,
        notes="OpenAlex paper collection.",
    ),
    ServiceDefinition(
        name="reddit_discovery",
        kind="153_dagu",
        schedule="0 0,12 * * *",
        owner_path="/root/python_project/dags/discovery.yaml",
        output_tables=("analytics.media_reddit_post",),
        article_source_types=("reddit",),
        critical=False,
        notes="Reddit discovery and subreddit refresh.",
    ),
    ServiceDefinition(
        name="finance",
        kind="153_dagu",
        schedule="0 3,15 * * *",
        owner_path="/root/python_project/dags/finance.yaml",
        output_tables=("analytics.finance_*",),
        critical=False,
        notes="Financial signal collection; tracked for health but not inserted into articles_v2.",
    ),
    ServiceDefinition(
        name="health_report",
        kind="153_dagu",
        schedule="0 8 * * *",
        owner_path="/root/python_project/dags/health_report.yaml",
        output_tables=(),
        critical=False,
        notes="Remote crawler health report.",
    ),
    ServiceDefinition(
        name="github_hf_live",
        kind="local_v2",
        schedule="on demand / long_task_runner --collect-live",
        owner_path="vectordbz_v2.collectors",
        output_tables=("analytics_v2.articles",),
        article_source_types=("github_repo", "hf_model", "hf_dataset", "hf_space"),
        critical=False,
        notes="Native V2 GitHub and Hugging Face source-aware collection.",
    ),
]

ARTICLE_SOURCE_TYPES = {
    source_type
    for service in UPSTREAM_SERVICES
    for source_type in service.article_source_types
}


def service_names(services: list[ServiceDefinition] | tuple[ServiceDefinition, ...]) -> list[str]:
    return [service.name for service in services]


def validate_article_source_coverage(source_types: set[str]) -> list[str]:
    """Return article source types missing from a candidate V2 source set."""
    return sorted(ARTICLE_SOURCE_TYPES - set(source_types))


def registry_as_dicts() -> list[dict]:
    return [
        {
            "name": service.name,
            "kind": service.kind,
            "schedule": service.schedule,
            "owner_path": service.owner_path,
            "output_tables": list(service.output_tables),
            "article_source_types": list(service.article_source_types),
            "critical": service.critical,
            "notes": service.notes,
        }
        for service in UPSTREAM_SERVICES
    ]
