from app.integrations.providers.base import ProviderError, ProviderErrorCode, ProviderStatus

_STATUS_ALIASES = {
    "submitted": ProviderStatus.SUBMITTED,
    "accepted": ProviderStatus.SUBMITTED,
    "created": ProviderStatus.SUBMITTED,
    "processing": ProviderStatus.PROCESSING,
    "in_production": ProviderStatus.PROCESSING,
    "production": ProviderStatus.PROCESSING,
    "fulfillment": ProviderStatus.FULFILLMENT,
    "in_fulfillment": ProviderStatus.FULFILLMENT,
    "shipped": ProviderStatus.SHIPPED,
    "shipping": ProviderStatus.SHIPPED,
    "completed": ProviderStatus.COMPLETED,
    "delivered": ProviderStatus.COMPLETED,
    "failed": ProviderStatus.FAILED,
    "error": ProviderStatus.FAILED,
}

def normalize_status(raw_status: str) -> ProviderStatus:
    if not isinstance(raw_status, str) or not raw_status.strip():
        raise ValueError("provider status is required")
    try:
        return _STATUS_ALIASES[raw_status.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"unsupported provider status: {raw_status}") from exc


def normalize_error(error: Exception | str) -> ProviderError:
    message = str(error).strip() or "provider error"
    lowered = message.lower()

    if any(token in lowered for token in ("timeout", "timed out")):
        return ProviderError(ProviderErrorCode.TIMEOUT, message, retryable=True)
    if any(token in lowered for token in ("429", "rate limit", "too many requests")):
        return ProviderError(ProviderErrorCode.RATE_LIMITED, message, retryable=True)
    if any(token in lowered for token in ("401", "403", "unauthorized", "forbidden", "api key")):
        return ProviderError(ProviderErrorCode.AUTHENTICATION, message)
    if any(token in lowered for token in ("400", "422", "invalid", "validation")):
        return ProviderError(ProviderErrorCode.VALIDATION, message)
    if any(token in lowered for token in ("502", "503", "504", "unavailable", "connection")):
        return ProviderError(ProviderErrorCode.UNAVAILABLE, message, retryable=True)
    return ProviderError(ProviderErrorCode.UNKNOWN, message)
