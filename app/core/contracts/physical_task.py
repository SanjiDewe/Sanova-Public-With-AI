from dataclasses import dataclass


@dataclass(frozen=True)
class PhysicalTaskSpec:
    intent: str
    action: str
    product: str
    asset: str | None = None
    destination: str | None = None
    quantity: int = 1
    provider: str | None = None

    def validate(self) -> None:
        if not self.intent.strip():
            raise ValueError("intent is required")
        if not self.action.strip():
            raise ValueError("action is required")
        if not self.product.strip():
            raise ValueError("product is required")
        if self.quantity < 1:
            raise ValueError("quantity must be >= 1")
        if self.action == "manufacture_and_fulfill" and not self.destination:
            raise ValueError("destination is required for manufacture_and_fulfill")
