import os
from dataclasses import dataclass
from urllib.parse import urlparse

from collections.abc import Mapping


@dataclass(frozen=True)
class RuntimeConfig:
    """Explicit runtime safety configuration.

    Configuration is resolved when a runtime component is constructed, not
    when this module is imported. This prevents import order from deciding
    execution policy.
    """

    environment: str = "sandbox"
    live_execution: bool = False

    def assert_sandbox_only(self) -> None:
        if self.environment != "sandbox" or self.live_execution:
            raise RuntimeError(
                "SANOVA v0 is sandbox-only. Live execution is intentionally blocked."
            )


def _env(name: str, environ: Mapping[str, str] | None = None) -> str | None:
    source = os.environ if environ is None else environ
    value = source.get(name)
    return value.strip() if value and value.strip() else None


def load_runtime_config(environ: Mapping[str, str] | None = None) -> RuntimeConfig:
    environment = (_env("SANOVA_ENVIRONMENT", environ) or "sandbox").strip().lower()
    raw_live = (_env("SANOVA_LIVE_EXECUTION", environ) or "false").strip().lower()
    if raw_live not in {"true", "false"}:
        raise ValueError("SANOVA_LIVE_EXECUTION must be exactly true or false.")
    config = RuntimeConfig(environment=environment, live_execution=raw_live == "true")
    config.assert_sandbox_only()
    return config


def super_admin_access_code(environ: Mapping[str, str] | None = None) -> str | None:
    """Return the privileged-area gate code from runtime environment."""
    return _env("SANOVA_SUPER_ADMIN_ACCESS_CODE", environ)


# Compatibility values for callers that still import these names. Runtime
# decisions must use load_runtime_config() instead of these module constants.
ENVIRONMENT = "sandbox"
LIVE_EXECUTION = False


@dataclass(frozen=True)
class SandboxProviderConfig:
    api_key: str | None
    base_url: str | None
    http_enabled: bool


def _sandbox_config(key_name: str, url_name: str) -> SandboxProviderConfig:
    enabled = _env("SANOVA_SANDBOX_HTTP_ENABLED") == "true"
    return SandboxProviderConfig(
        api_key=_env(key_name),
        base_url=_env(url_name),
        http_enabled=enabled,
    )


def provider_config(provider: str) -> SandboxProviderConfig:
    configs = {
        "prodigi": _sandbox_config("SANOVA_PRODIGI_SANDBOX_API_KEY", "SANOVA_PRODIGI_SANDBOX_BASE_URL"),
        "cloudprinter": _sandbox_config("SANOVA_CLOUDPRINTER_SANDBOX_API_KEY", "SANOVA_CLOUDPRINTER_SANDBOX_BASE_URL"),
    }
    try:
        return configs[provider]
    except KeyError as exc:
        raise ValueError(f"Unsupported provider: {provider}") from exc


SANDBOX_PROVIDER_HOSTS = {
    # Prodigi exposes a dedicated sandbox hostname.
    "prodigi": frozenset({"api.sandbox.prodigi.com"}),
    # Cloudprinter uses the CloudCore hostname for both modes; sandbox safety
    # therefore depends on the sandbox API interface/key as well as this
    # exact host allowlist. Never accept arbitrary Cloudprinter subdomains.
    "cloudprinter": frozenset({"api.cloudprinter.com"}),
}


def assert_sandbox_url(url: str, provider: str | None = None) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError("Sandbox provider URL must use HTTPS and include a host.")

    host = parsed.hostname.lower() if parsed.hostname else ""
    if not provider:
        raise RuntimeError("Sandbox provider must be specified for URL validation.")

    try:
        allowed_hosts = SANDBOX_PROVIDER_HOSTS[provider]
    except KeyError as exc:
        raise ValueError(f"Unsupported provider: {provider}") from exc

    forbidden_live_hosts = {
        "api.prodigi.com",
        "prodigi.com",
        "api.cloudprinter.com",
        "cloudprinter.com",
    }
    # Cloudprinter intentionally uses the same exact CloudCore hostname for
    # sandbox/live account modes; its sandbox API interface/key must therefore
    # be used whenever this exact host is configured. Other known production
    # hosts remain unconditionally forbidden.
    if host in forbidden_live_hosts:
        if provider == "cloudprinter" and host == "api.cloudprinter.com":
            return
        raise RuntimeError("live API host is forbidden in sandbox mode.")

    if host not in allowed_hosts:
        raise RuntimeError(f"URL host is not allowlisted for {provider} sandbox mode.")

@dataclass(frozen=True)
class EmailProviderConfig:
    api_key: str | None
    base_url: str
    from_email: str | None
    timeout_seconds: float


def email_provider_config(provider: str) -> EmailProviderConfig:
    key = provider.strip().lower()
    if key == "brevo":
        return EmailProviderConfig(
            api_key=_env("SANOVA_BREVO_API_KEY"),
            base_url=_env("SANOVA_BREVO_BASE_URL") or "https://api.brevo.com/v3",
            from_email=_env("SANOVA_EMAIL_FROM"),
            timeout_seconds=float(_env("SANOVA_EMAIL_TIMEOUT_SECONDS") or "15"),
        )
    if key == "mock":
        return EmailProviderConfig(None, "mock://", _env("SANOVA_EMAIL_FROM"), 1.0)
    raise ValueError(f"Unsupported email provider: {provider}")


@dataclass(frozen=True)
class OAuthProviderConfig:
    client_id: str | None
    client_secret: str | None
    redirect_uri: str | None
    authorization_url: str
    token_url: str
    revoke_url: str
    userinfo_url: str
    scopes: tuple[str, ...]
    timeout_seconds: float


def oauth_provider_config(provider: str) -> OAuthProviderConfig:
    key = provider.strip().lower()
    if key == "google":
        scopes = tuple(
            value.strip()
            for value in (_env("SANOVA_GOOGLE_OAUTH_SCOPES") or "openid,email,profile,https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/calendar,https://www.googleapis.com/auth/spreadsheets").split(",")
            if value.strip()
        )
        return OAuthProviderConfig(
            client_id=_env("SANOVA_GOOGLE_CLIENT_ID"),
            client_secret=_env("SANOVA_GOOGLE_CLIENT_SECRET"),
            redirect_uri=_env("SANOVA_GOOGLE_REDIRECT_URI"),
            authorization_url=_env("SANOVA_GOOGLE_AUTHORIZATION_URL") or "https://accounts.google.com/o/oauth2/v2/auth",
            token_url=_env("SANOVA_GOOGLE_TOKEN_URL") or "https://oauth2.googleapis.com/token",
            revoke_url=_env("SANOVA_GOOGLE_REVOKE_URL") or "https://oauth2.googleapis.com/revoke",
            userinfo_url=_env("SANOVA_GOOGLE_USERINFO_URL") or "https://openidconnect.googleapis.com/v1/userinfo",
            scopes=scopes,
            timeout_seconds=float(_env("SANOVA_OAUTH_TIMEOUT_SECONDS") or "15"),
        )
    if key == "mock":
        return OAuthProviderConfig(None, None, None, "mock://authorize", "mock://token", "mock://revoke", "mock://userinfo", (), 1.0)
    raise ValueError(f"Unsupported OAuth provider: {provider}")
