import pytest
from fastapi.testclient import TestClient

from app.web.app import create_app
from app.integrations.email.mock import MockEmailProvider
import re

PASSWORD = "correct horse battery staple"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SANOVA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SANOVA_IDENTITY_DB", str(tmp_path / "identity.sqlite3"))
    monkeypatch.setenv("SANOVA_STATE_DIR", str(tmp_path / "tasks"))
    monkeypatch.setenv("SANOVA_AUDIT_DIR", str(tmp_path / "audit"))
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_public_routes_are_public_and_private_dashboard_requires_login(client):
    assert client.get("/").status_code == 200
    assert client.get("/privacy").status_code == 200
    assert client.get("/terms").status_code == 200
    response = client.get("/app", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_signup_login_and_private_ui(client):
    response = client.post("/signup", data={"email": "user@example.com", "password": PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/verify-email?email=")
    code = re.search(r"\b(\d{6})\b", MockEmailProvider.sent[-1].text).group(1)
    response = client.post("/verify-email", data={"email": "user@example.com", "code": code}, follow_redirects=False)
    assert response.status_code == 303
    response = client.post("/login", data={"email": "user@example.com", "password": PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    assert "sanova_session=" in response.headers.get("set-cookie", "")
    client.cookies.update(response.cookies)
    assert client.get("/app").status_code == 200
    execute_page = client.get("/app/execute")
    assert execute_page.status_code == 200
    assert 'name="provider"' in execute_page.text
    assert client.get("/app/settings").status_code == 200


def test_ui_uses_i18n_locale_cookie(client):
    client.cookies.set("sanova_locale", "id")
    response = client.get("/")
    assert "Cara yang lebih cerdas untuk bekerja dengan AI." in response.text
    assert "A smarter way to work with AI." not in response.text


def test_execution_ui_uses_existing_application_pipeline(client):
    client.post("/signup", data={"email": "runner@example.com", "password": PASSWORD})
    code = re.search(r"\b(\d{6})\b", MockEmailProvider.sent[-1].text).group(1)
    client.post("/verify-email", data={"email": "runner@example.com", "code": code})
    client.post("/login", data={"email": "runner@example.com", "password": PASSWORD})
    response = client.post("/app/execute", data={"intent": "make 1 mug using design.png and ship to TEST-DESTINATION"})
    assert response.status_code == 200
    assert "submitted" in response.text
    assert "TEST-DESTINATION" not in response.text or "Execution result" in response.text


def test_super_admin_has_separate_access_code_and_login_gates(client, monkeypatch):
    monkeypatch.setenv("SANOVA_SUPER_ADMIN_ACCESS_CODE", "test-super-code")
    client.post("/signup", data={"email": "user2@example.com", "password": PASSWORD})
    code = re.search(r"\b(\d{6})\b", MockEmailProvider.sent[-1].text).group(1)
    client.post("/verify-email", data={"email": "user2@example.com", "code": code})

    response = client.get("/super-admin")
    assert response.status_code == 401
    assert "Super Admin Access Code" in response.text
    assert 'name="email"' not in response.text
    assert 'name="password"' not in response.text

    response = client.post("/super-admin/access", data={"access_code": "wrong"})
    assert response.status_code == 401

    response = client.post("/super-admin/access", data={"access_code": "test-super-code"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/super-admin/login"

    response = client.get("/super-admin/login")
    assert response.status_code == 401
    assert 'name="email"' in response.text
    assert 'name="password"' in response.text
    assert "Super Admin Access Code" not in response.text

    response = client.post("/super-admin/login", data={"email": "user2@example.com", "password": PASSWORD})
    assert response.status_code == 403


def _signup_and_login(client, email):
    response = client.post("/signup", data={"email": email, "password": PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    code = re.search(r"\b(\d{6})\b", MockEmailProvider.sent[-1].text).group(1)
    response = client.post("/verify-email", data={"email": email, "code": code}, follow_redirects=False)
    assert response.status_code == 303
    response = client.post("/login", data={"email": email, "password": PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    client.cookies.update(response.cookies)


def test_health_endpoint_matches_deployment_contract(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_login_rejects_external_redirect_targets(client):
    _signup_and_login(client, "redirect@example.com")
    client.post("/logout", follow_redirects=False)
    response = client.post(
        "/login",
        data={"email": "redirect@example.com", "password": PASSWORD, "next": "//evil.example/path"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/app"


def test_tasks_are_scoped_to_the_authenticated_owner(client):
    _signup_and_login(client, "owner-a@example.com")
    response = client.post(
        "/app/execute",
        data={"intent": "make 1 mug using design.png and ship to DEST-A"},
    )
    assert response.status_code == 200
    paths = list((client.app.state.sanova.execution_store.root).glob("*.json"))
    assert paths
    record = __import__("json").loads(paths[0].read_text(encoding="utf-8"))
    task_id = record["task"]["id"]
    owner_id = record["task"]["owner_id"]
    assert owner_id

    client.post("/logout", follow_redirects=False)
    _signup_and_login(client, "owner-b@example.com")
    tasks_page = client.get("/app/tasks")
    assert tasks_page.status_code == 200
    assert task_id not in tasks_page.text

    webhook = client.post(
        f"/app/tasks/{task_id}/webhook",
        data={"status": "processing"},
        follow_redirects=False,
    )
    assert webhook.status_code == 303
    assert webhook.headers["location"].endswith("webhook_error=Task%20not%20found")
    current = __import__("json").loads(paths[0].read_text(encoding="utf-8"))
    assert current["task"]["owner_id"] == owner_id
    assert current["task"]["state"] == record["task"]["state"]
