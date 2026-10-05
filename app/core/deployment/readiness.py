from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class DeploymentIssue:
    code: str
    message: str


@dataclass(frozen=True)
class DeploymentReport:
    safe: bool
    issues: tuple[DeploymentIssue, ...]

    @property
    def production_locked(self) -> bool:
        return True


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if value else ""


def evaluate() -> DeploymentReport:
    """Read-only deployment configuration checks."""
    issues: list[DeploymentIssue] = []

    environment = _env("SANOVA_ENVIRONMENT", "sandbox").lower()
    live_execution = _env("SANOVA_LIVE_EXECUTION", "false").lower()
    sandbox_http = _env("SANOVA_SANDBOX_HTTP_ENABLED", "false").lower()

    if environment != "sandbox":
        issues.append(DeploymentIssue(
            "environment_not_sandbox",
            "deployment environment must remain sandbox",
        ))

    if live_execution != "false":
        issues.append(DeploymentIssue(
            "live_execution_not_disabled",
            "SANOVA_LIVE_EXECUTION must be exactly false",
        ))

    # Sandbox HTTP may be enabled for integration testing. The production
    # boundary remains locked by SANOVA_ENVIRONMENT=sandbox and
    # SANOVA_LIVE_EXECUTION=false.

    forbidden = (
        "SANOVA_PRODIGI_API_KEY",
        "SANOVA_CLOUDPRINTER_API_KEY",
        "SANOVA_PRODUCTION_API_KEY",
        "SANOVA_PRODUCTION_SECRET",
    )
    for name in forbidden:
        if _env(name):
            issues.append(DeploymentIssue(
                "production_credential_present",
                f"{name} must not be present in the sandbox deployment",
            ))

    return DeploymentReport(safe=not issues, issues=tuple(issues))
