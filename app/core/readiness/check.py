from __future__ import annotations

from dataclasses import dataclass
import os

from app.config import assert_sandbox_url
from app.core.orchestration.router import ProviderRouter


@dataclass(frozen=True)
class ReadinessIssue:
    code: str
    message: str


@dataclass(frozen=True)
class ReadinessReport:
    sandbox_safe: bool
    production_locked: bool
    issues: tuple[ReadinessIssue, ...]

    @property
    def ready_for_controlled_testing(self) -> bool:
        return self.sandbox_safe and not self.issues


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if value else ""


def evaluate() -> ReadinessReport:
    """Evaluate deployment safety without enabling production execution.

    This is a read-only readiness check. It does not contact providers,
    change configuration, or alter the execution state.
    """
    issues: list[ReadinessIssue] = []

    environment = _env("SANOVA_ENVIRONMENT", "sandbox").lower()
    live_execution = _env("SANOVA_LIVE_EXECUTION", "false").lower() == "true"
    http_enabled = _env("SANOVA_SANDBOX_HTTP_ENABLED", "false").lower() == "true"

    if environment != "sandbox":
        issues.append(
            ReadinessIssue(
                "environment_not_sandbox",
                "SANOVA_ENVIRONMENT must remain 'sandbox'.",
            )
        )

    if live_execution:
        issues.append(
            ReadinessIssue(
                "live_execution_enabled",
                "SANOVA_LIVE_EXECUTION must remain false.",
            )
        )

    # Sandbox HTTP is an explicit testing capability. It is allowed only while
    # the environment remains sandbox and live execution remains disabled.

    # If URLs are configured, validate them without making network requests.
    for provider, name in (
        ("prodigi", "SANOVA_PRODIGI_SANDBOX_BASE_URL"),
        ("cloudprinter", "SANOVA_CLOUDPRINTER_SANDBOX_BASE_URL"),
    ):
        value = _env(name)
        if value:
            try:
                assert_sandbox_url(value, provider)
            except Exception as exc:
                issues.append(ReadinessIssue("unsafe_provider_url", f"{name}: {exc}"))

    # Provider construction is configuration-driven. This check only inspects
    # the selected mode; it performs no provider I/O.
    try:
        router = ProviderRouter()
        expected_simulation = not http_enabled
        for provider_name in ("prodigi", "cloudprinter"):
            provider = router.registry.get(provider_name)
            if getattr(provider, "simulation", True) is not expected_simulation:
                issues.append(
                    ReadinessIssue(
                        "provider_simulation_mode_mismatch",
                        f"{provider_name} sandbox adapter does not match SANOVA_SANDBOX_HTTP_ENABLED.",
                    )
                )
    except Exception as exc:
        issues.append(ReadinessIssue("provider_boundary_error", str(exc)))

    return ReadinessReport(
        sandbox_safe=not any(
            issue.code in {
                "environment_not_sandbox",
                "live_execution_enabled",
                "unsafe_provider_url",
                "provider_simulation_mode_mismatch",
                "provider_boundary_error",
            }
            for issue in issues
        ),
        # Production remains explicitly locked regardless of the report.
        production_locked=True,
        issues=tuple(issues),
    )
