import pytest

def test_default_is_sandbox():
    from app.config import load_runtime_config
    config = load_runtime_config({})
    assert config.environment == "sandbox"
    assert config.live_execution is False

def test_live_mode_is_hard_blocked_at_runtime_resolution():
    from app.config import load_runtime_config
    with pytest.raises(RuntimeError):
        load_runtime_config({"SANOVA_ENVIRONMENT": "live", "SANOVA_LIVE_EXECUTION": "true"})

def test_invalid_live_execution_value_is_rejected():
    from app.config import load_runtime_config
    with pytest.raises(ValueError):
        load_runtime_config({"SANOVA_LIVE_EXECUTION": "yes"})
