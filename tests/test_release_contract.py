from pathlib import Path


def test_readme_documents_current_release_contract():
    root = Path(__file__).resolve().parents[1]
    text = (root / "README.md").read_text(encoding="utf-8")
    required = (
        "RuntimeConfig",
        "SANOVA_ENVIRONMENT=sandbox",
        "SANOVA_LIVE_EXECUTION=false",
        "SANOVA_SANDBOX_HTTP_ENABLED=false",
        "Provider factories are lazy",
        "scripts/build_artifact.py",
        "rotate/revoke",
    )
    for item in required:
        assert item in text


def test_deployment_contract_documents_release_acceptance():
    root = Path(__file__).resolve().parents[1]
    text = (root / "DEPLOYMENT.md").read_text(encoding="utf-8")
    required = (
        "load_runtime_config()",
        "RuntimeConfig",
        "pytest -q",
        "python -m compileall app tests",
        "scripts/build_artifact.py",
        "Do not automatically retry an `IN_FLIGHT` task",
        "Release acceptance",
    )
    for item in required:
        assert item in text
