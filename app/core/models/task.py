from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4


class TaskState(str, Enum):
    CREATED = "created"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    FULFILLMENT = "fulfillment"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PhysicalTask:
    intent: str
    provider: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    state: TaskState = TaskState.CREATED
    external_id: str | None = None
    action: str | None = None
    product: str | None = None
    asset: str | None = None
    destination: str | None = None
    quantity: int = 1
    owner_id: str | None = None
