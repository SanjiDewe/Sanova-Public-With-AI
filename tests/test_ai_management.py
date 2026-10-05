import pytest

from app.ai.credentials import AICredentialCipher
from app.ai.management import AIProviderManagement
from app.ai.provider import AIProviderRegistry, OpenAIProvider
from app.identity import IdentityService, IdentityStore

PASSWORD = "correct horse battery staple"


def make_manager(tmp_path):
    store = IdentityStore()
    identity = IdentityService(store)
    admin = store.create_user("admin@example.com", identity.passwords.hash(PASSWORD), role="admin")
    user = identity.register("user@example.com", PASSWORD)
    admin_token = identity.authenticate(admin.email, PASSWORD)
    user_token = identity.authenticate(user.email, PASSWORD)
    registry = AIProviderRegistry()
    cipher = AICredentialCipher(key=b"test-ai-credential-key")
    manager = AIProviderManagement(identity, store, registry, cipher=cipher)
    return store, manager, registry, admin_token, user_token


def test_ai_credential_is_encrypted_and_masked(tmp_path):
    cipher = AICredentialCipher(key=b"test-ai-credential-key")
    token = cipher.encrypt("sk-secret-value")
    assert token != "sk-secret-value"
    assert cipher.decrypt(token) == "sk-secret-value"


def test_ai_provider_connect_discovers_models_and_refreshes_runtime(monkeypatch, tmp_path):
    store, manager, registry, admin_token, _ = make_manager(tmp_path)
    monkeypatch.setattr(OpenAIProvider, "discover_models", lambda self: ("gpt-test", "gpt-test-mini"))

    view = manager.connect(manager.identity.current_user(admin_token), "openai", "sk-secret-value")

    assert view.enabled is False
    assert view.status == "connected"
    assert view.models == ("gpt-test", "gpt-test-mini")
    assert registry.names() == ()
    assert view.models == ("gpt-test", "gpt-test-mini")
    stored = store.get_ai_provider_config("openai")
    assert stored["credential"] != "sk-secret-value"
    assert "sk-secret-value" not in repr(stored)
    store.close()


def test_ai_provider_disable_and_revoke_remove_runtime_access(monkeypatch, tmp_path):
    store, manager, registry, admin_token, _ = make_manager(tmp_path)
    actor = manager.identity.current_user(admin_token)
    monkeypatch.setattr(OpenAIProvider, "discover_models", lambda self: ("gpt-test",))
    manager.connect(actor, "openai", "sk-secret-value")
    assert registry.names() == ()

    manager.enable(actor, "openai")
    assert registry.names() == ("openai",)

    manager.disable(actor, "openai")
    assert registry.names() == ()
    assert store.get_ai_provider_config("openai")["status"] == "disabled"

    manager.enable(actor, "openai")
    assert registry.names() == ("openai",)

    manager.revoke(actor, "openai")
    assert registry.names() == ()
    row = store.get_ai_provider_config("openai")
    assert row["credential"] is None
    assert row["status"] == "revoked"
    store.close()


def test_ai_provider_replacement_validates_before_swapping(monkeypatch, tmp_path):
    store, manager, registry, admin_token, _ = make_manager(tmp_path)
    actor = manager.identity.current_user(admin_token)
    calls = []

    def discover(self):
        calls.append(self.api_key)
        if self.api_key == "bad":
            raise RuntimeError("invalid credential")
        return ("gpt-new",)

    monkeypatch.setattr(OpenAIProvider, "discover_models", discover)
    manager.connect(actor, "openai", "good")
    manager.enable(actor, "openai")
    original = store.get_ai_provider_config("openai")["credential"]

    with pytest.raises(RuntimeError):
        manager.replace(actor, "openai", "bad")
    assert store.get_ai_provider_config("openai")["credential"] == original
    assert registry.models("openai")[0].model == "gpt-new"
    assert calls == ["good", "bad"]
    store.close()


def test_ai_provider_management_requires_provider_permission(tmp_path):
    store, manager, _, _, user_token = make_manager(tmp_path)
    with pytest.raises(PermissionError):
        manager.list(manager.identity.current_user(user_token))
    store.close()


def test_connect_requires_explicit_enable(monkeypatch, tmp_path):
    store, manager, registry, admin_token, _ = make_manager(tmp_path)
    actor = manager.identity.current_user(admin_token)
    monkeypatch.setattr(OpenAIProvider, "discover_models", lambda self: ("gpt-test",))
    view = manager.connect(actor, "openai", "new-key")
    assert view.status == "connected"
    assert view.enabled is False
    assert registry.names() == ()
    enabled = manager.enable(actor, "openai")
    assert enabled.status == "active"
    assert registry.names() == ("openai",)
    store.close()

def test_replace_preserves_enabled_state(monkeypatch, tmp_path):
    store, manager, registry, admin_token, _ = make_manager(tmp_path)
    actor = manager.identity.current_user(admin_token)
    monkeypatch.setattr(OpenAIProvider, "discover_models", lambda self: ("gpt-test",))
    manager.connect(actor, "openai", "old")
    replaced = manager.replace(actor, "openai", "new")
    assert replaced.status == "connected"
    assert replaced.enabled is False
    manager.enable(actor, "openai")
    replaced = manager.replace(actor, "openai", "newer")
    assert replaced.status == "active"
    assert replaced.enabled is True
    assert registry.names() == ("openai",)
    store.close()
