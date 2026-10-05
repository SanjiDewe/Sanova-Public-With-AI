import os

from app.deployment.readiness import evaluate


def test_default_deployment_is_sandbox_safe(monkeypatch):
    for name in (
        "SANOVA_ENVIRONMENT",
        "SANOVA_LIVE_EXECUTION",
        "SANOVA_SANDBOX_HTTP_ENABLED",
        "SANOVA_PRODIGI_API_KEY",
        "SANOVA_CLOUDPRINTER_API_KEY",
        "SANOVA_PRODUCTION_API_KEY",
        "SANOVA_PRODUCTION_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    report = evaluate()
    assert report.safe is True
    assert report.production_locked is True
    assert report.issues == ()


def test_non_sandbox_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "staging")
    monkeypatch.setenv("SANOVA_LIVE_EXECUTION", "false")
    monkeypatch.setenv("SANOVA_SANDBOX_HTTP_ENABLED", "false")

    report = evaluate()

    assert report.safe is False
    assert any(i.code == "environment_not_sandbox" for i in report.issues)


def test_live_execution_must_be_exactly_false(monkeypatch):
    monkeypatch.setenv("SANOVA_LIVE_EXECUTION", "true")

    report = evaluate()

    assert report.safe is False
    assert any(i.code == "live_execution_not_disabled" for i in report.issues)


def test_sandbox_http_is_allowed_for_integration_testing(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("SANOVA_LIVE_EXECUTION", "false")
    monkeypatch.setenv("SANOVA_SANDBOX_HTTP_ENABLED", "true")

    report = evaluate()

    assert report.safe is True
    assert report.production_locked is True


def test_production_provider_key_is_rejected(monkeypatch):
    monkeypatch.setenv("SANOVA_PRODIGI_API_KEY", "present")

    report = evaluate()

    assert report.safe is False
    assert any(i.code == "production_credential_present" for i in report.issues)


def test_cloudprinter_production_key_is_rejected(monkeypatch):
    monkeypatch.setenv("SANOVA_CLOUDPRINTER_API_KEY", "present")

    report = evaluate()

    assert report.safe is False
    assert any(i.code == "production_credential_present" for i in report.issues)


def test_generic_production_credentials_are_rejected(monkeypatch):
    monkeypatch.setenv("SANOVA_PRODUCTION_API_KEY", "present")

    report = evaluate()

    assert report.safe is False
    assert any(i.code == "production_credential_present" for i in report.issues)


def test_readiness_is_observer_only(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("SANOVA_LIVE_EXECUTION", "false")
    monkeypatch.setenv("SANOVA_SANDBOX_HTTP_ENABLED", "false")

    before = dict(os.environ)
    report = evaluate()

    assert report.production_locked is True
    assert dict(os.environ) == before
