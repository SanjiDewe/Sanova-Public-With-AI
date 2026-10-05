from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from app.core.models.task import PhysicalTask


class ProviderStatus(str, Enum):
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    FULFILLMENT = "fulfillment"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    FAILED = "failed"


class ProviderErrorCode(str, Enum):
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProviderError:
    code: ProviderErrorCode
    message: str
    retryable: bool = False


@dataclass(frozen=True)
class ProviderResult:
    accepted: bool
    status: ProviderStatus | None = None
    external_id: str | None = None
    message: str = ""
    error: ProviderError | None = None

    @property
    def failed(self) -> bool:
        return not self.accepted or self.error is not None


class PhysicalProvider(ABC):
    name: str

    @abstractmethod
    def submit_sandbox(self, task: PhysicalTask) -> ProviderResult:
        raise NotImplementedError

    @abstractmethod
    def normalize_status(self, raw_status: str) -> ProviderStatus:
        raise NotImplementedError

    @abstractmethod
    def normalize_error(self, error: Exception | str) -> ProviderError:
        raise NotImplementedError
