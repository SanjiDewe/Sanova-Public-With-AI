from app.readiness.check import evaluate


def test_default_runtime_is_safe_for_controlled_testing(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("SANOVA_LIVE_EXECUTION", "false")
    monkeypatch.setenv("SANOVA_SANDBOX_HTTP_ENABLED", "false")

    report = evaluate()

    assert report.sandbox_safe is True
    assert report.production_locked is True
    assert report.ready_for_controlled_testing is True
    assert report.issues == ()


def test_non_sandbox_environment_is_blocked(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "production")
    monkeypatch.setenv("SANOVA_LIVE_EXECUTION", "false")
    monkeypatch.setenv("SANOVA_SANDBOX_HTTP_ENABLED", "false")

    report = evaluate()

    assert report.sandbox_safe is False
    assert report.production_locked is True
    assert any(i.code == "environment_not_sandbox" for i in report.issues)


def test_live_execution_is_blocked(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("SANOVA_LIVE_EXECUTION", "true")
    monkeypatch.setenv("SANOVA_SANDBOX_HTTP_ENABLED", "false")

    report = evaluate()

    assert report.sandbox_safe is False
    assert report.production_locked is True
    assert any(i.code == "live_execution_enabled" for i in report.issues)


def test_sandbox_http_is_allowed_for_integration_testing(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("SANOVA_LIVE_EXECUTION", "false")
    monkeypatch.setenv("SANOVA_SANDBOX_HTTP_ENABLED", "true")
    monkeypatch.setenv("SANOVA_PRODIGI_SANDBOX_BASE_URL", "https://api.sandbox.prodigi.com")
    monkeypatch.setenv("SANOVA_CLOUDPRINTER_SANDBOX_BASE_URL", "https://api.cloudprinter.com")

    report = evaluate()

    assert report.sandbox_safe is True
    assert report.production_locked is True
    assert report.issues == ()


def test_configured_live_provider_url_is_rejected(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("SANOVA_LIVE_EXECUTION", "false")
    monkeypatch.setenv("SANOVA_SANDBOX_HTTP_ENABLED", "false")
    monkeypatch.setenv(
        "SANOVA_PRODIGI_SANDBOX_BASE_URL",
        "https://api.prodigi.com",
    )

    report = evaluate()

    assert report.sandbox_safe is False
    assert any(i.code == "unsafe_provider_url" for i in report.issues)


def test_configured_sandbox_urls_are_checked_without_network(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("SANOVA_LIVE_EXECUTION", "false")
    monkeypatch.setenv("SANOVA_SANDBOX_HTTP_ENABLED", "false")
    monkeypatch.setenv(
        "SANOVA_PRODIGI_SANDBOX_BASE_URL",
        "https://api.sandbox.prodigi.com",
    )

    report = evaluate()

    assert report.sandbox_safe is True
    assert report.production_locked is True
    assert report.issues == ()


def test_default_provider_adapters_remain_simulation_only(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("SANOVA_LIVE_EXECUTION", "false")
    monkeypatch.setenv("SANOVA_SANDBOX_HTTP_ENABLED", "false")

    report = evaluate()

    assert report.sandbox_safe is True
    assert report.production_locked is True


def test_readiness_check_does_not_enable_production(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("SANOVA_LIVE_EXECUTION", "false")
    monkeypatch.setenv("SANOVA_SANDBOX_HTTP_ENABLED", "false")

    report = evaluate()

    assert report.production_locked is True
    assert report.ready_for_controlled_testing is True
