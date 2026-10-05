import pytest

from app.providers.base import ProviderErrorCode, ProviderStatus
from app.providers.normalization import normalize_error, normalize_status
from app.providers.prodigi import ProdigiSandboxAdapter
from app.providers.cloudprinter import CloudprinterSandboxAdapter


def test_provider_statuses_normalize_to_one_internal_language():
    assert normalize_status("accepted") is ProviderStatus.SUBMITTED
    assert normalize_status("in_production") is ProviderStatus.PROCESSING
    assert normalize_status("in_fulfillment") is ProviderStatus.FULFILLMENT
    assert normalize_status("shipping") is ProviderStatus.SHIPPED
    assert normalize_status("delivered") is ProviderStatus.COMPLETED


def test_unknown_status_is_rejected():
    with pytest.raises(ValueError):
        normalize_status("something_new")


@pytest.mark.parametrize(
    ("message", "code", "retryable"),
    [
        ("request timed out", ProviderErrorCode.TIMEOUT, True),
        ("429 rate limit", ProviderErrorCode.RATE_LIMITED, True),
        ("401 unauthorized", ProviderErrorCode.AUTHENTICATION, False),
        ("422 validation failed", ProviderErrorCode.VALIDATION, False),
        ("503 unavailable", ProviderErrorCode.UNAVAILABLE, True),
    ],
)
def test_errors_are_normalized(message, code, retryable):
    error = normalize_error(message)
    assert error.code is code
    assert error.retryable is retryable


@pytest.mark.parametrize("adapter", [ProdigiSandboxAdapter(), CloudprinterSandboxAdapter()])
def test_each_provider_exposes_the_same_normalization_contract(adapter):
    assert adapter.normalize_status("processing") is ProviderStatus.PROCESSING
    assert adapter.normalize_error("timeout").code is ProviderErrorCode.TIMEOUT
