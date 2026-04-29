def test_worker_modules_import_without_external_runtime_dependencies():
    import vectordbz_v2.embed_worker  # noqa: F401
    import vectordbz_v2.migrate  # noqa: F401
    import vectordbz_v2.trend_analyzer  # noqa: F401
