from app.core.contracts.intent import StructuredIntent
from app.core.contracts.physical_task import PhysicalTaskSpec
from app.core.models.task import PhysicalTask


class ExecutionPlanner:
    """Turns a validated task specification into a PhysicalTask.

    Planning never calls a provider and never performs execution.
    """

    def build(self, spec: PhysicalTaskSpec) -> PhysicalTask:
        spec.validate()
        return PhysicalTask(
            intent=spec.intent,
            provider=spec.provider,
            action=spec.action,
            product=spec.product,
            asset=spec.asset,
            destination=spec.destination,
            quantity=spec.quantity,
        )

    def build_from_intent(self, intent: StructuredIntent) -> PhysicalTask:
        """Convert interpreted intent into the existing planning contract."""
        intent.validate()
        spec = PhysicalTaskSpec(
            intent=intent.intent,
            action=intent.action,
            product=intent.product,
            asset=intent.asset,
            destination=intent.destination,
            quantity=intent.quantity,
            provider=intent.provider,
        )
        return self.build(spec)
