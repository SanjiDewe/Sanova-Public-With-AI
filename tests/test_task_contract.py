import pytest
from app.contracts.physical_task import PhysicalTaskSpec


def test_contract_accepts_valid_physical_task():
    spec = PhysicalTaskSpec(
        intent="make one mug and ship it",
        action="manufacture_and_fulfill",
        product="mug",
        asset="design.png",
        destination="TEST-DESTINATION",
    )
    spec.validate()


def test_contract_rejects_missing_destination():
    spec = PhysicalTaskSpec(
        intent="make one mug",
        action="manufacture_and_fulfill",
        product="mug",
    )
    with pytest.raises(ValueError):
        spec.validate()
