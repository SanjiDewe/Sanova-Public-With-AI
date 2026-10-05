from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.audit.trail import AuditTrail
from app.core.deployment.readiness import evaluate as deployment_readiness
from app.core.persistence.store import ExecutionStore
from app.core.readiness.check import evaluate as runtime_readiness
from app.core.orchestration.router import ProviderRouter
from app.identity import IdentityService, IdentityStore
from app.identity.authorization import Permission
from app.i18n import browser_locale, normalize_locale, translate
from app.integrations.providers.registry import physical_provider_registry
from app.management.router import ManagementRouter
from app.integrations.contracts.email import EmailMessage
from app.integrations.email.registry import build_email_registry
from app.identity.oauth import OAuthStateStore
from app.integrations.oauth.registry import build_oauth_registry
from app.integrations.accounts import ConnectedAccountStore
from app.integrations.google import GoogleService
from app.integrations.webhooks.handler import handle_provider_webhook
from app.core.models.task import PhysicalTask, TaskState
from app.core.orchestration.pipeline import EndToEndSimulation
from app.core.contracts.physical_task import PhysicalTaskSpec
from app.ai import AIAgent, AIConversationStore, build_ai_provider_registry, build_tool_registry
from app.ai.credentials import AICredentialCipher
from app.ai.management import AIProviderManagement
from app.config import super_admin_access_code
from app.integrations.providers.mock import MockProvider
from app.integrations.providers.prodigi import ProdigiSandboxAdapter
from app.integrations.providers.cloudprinter import CloudprinterSandboxAdapter

BASE = Path(__file__).parent
TEMPLATES = BASE / "templates"
STATIC = BASE / "static"


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() == "true"


class WebContext:
    def __init__(self) -> None:
        data_root = Path(os.getenv("SANOVA_DATA_DIR", "data"))
        data_root.mkdir(parents=True, exist_ok=True)
        db_path = os.getenv("SANOVA_IDENTITY_DB")
        database_url = os.getenv("DATABASE_URL")
        environment = os.getenv("SANOVA_ENVIRONMENT", "local").strip().lower()
        if not db_path and not database_url:
            if environment not in {"local", "test", "development"}:
                raise RuntimeError(
                    "DATABASE_URL is required outside local/test/development; "
                    "refusing to fall back to SQLite in deployment"
                )
            db_path = str(data_root / "identity.sqlite3")
        state_dir = os.getenv("SANOVA_STATE_DIR", str(data_root / "tasks"))
        audit_dir = os.getenv("SANOVA_AUDIT_DIR", str(data_root / "audit"))

        self.identity_store = IdentityStore(path=db_path, database_url=database_url)
        self.identity = IdentityService(self.identity_store)
        self.audit = AuditTrail(audit_dir)
        self.physical_registry = physical_provider_registry()
        self.email_registry = build_email_registry()
        self.oauth_registry = build_oauth_registry()
        self.oauth_states = OAuthStateStore(self.identity_store)
        self.connected_accounts = ConnectedAccountStore(self.identity_store)
        self.google = GoogleService(self.connected_accounts, self.oauth_registry.get("google"))
        self.provider_router = ProviderRouter(registry=self.physical_registry)
        self.execution_store = ExecutionStore(state_dir)
        from app.core.orchestration.executor import ExecutionEngine
        from app.core.application.service import ApplicationService as CoreApplicationService
        self.engine = ExecutionEngine(
            router=self.provider_router,
            store=self.execution_store,
            audit=self.audit,
        )
        self.application = CoreApplicationService(engine=self.engine)
        self.ai_providers = build_ai_provider_registry()
        self.ai_state_dir = Path(os.getenv("SANOVA_AI_STATE_DIR", str(data_root / "ai")))
        self.ai_store = AIConversationStore(self.ai_state_dir)
        self.ai_credential_cipher = AICredentialCipher(key_path=self.ai_state_dir / ".credential-key")
        self.ai_management = AIProviderManagement(
            self.identity, self.identity_store, self.ai_providers, cipher=self.ai_credential_cipher
        )
        for _ai_config in self.identity_store.list_ai_provider_configs():
            if _ai_config.get("enabled") and _ai_config.get("status") == "active":
                try:
                    self.ai_management._refresh(_ai_config["name"])
                except Exception:
                    self.identity_store.set_ai_provider_state(
                        _ai_config["name"], enabled=False, status="disabled", models=_ai_config.get("models", []),
                        selected_model=_ai_config.get("selected_model")
                    )
        self.ai_tools = build_tool_registry(tuple(self.physical_registry.names()), google=self.google)
        self.ai_agent = AIAgent(self.ai_providers, self.ai_tools, self.ai_store)
        self.management = ManagementRouter(
            self.identity,
            providers=__import__("app.management.providers", fromlist=["ProviderManagement"]).ProviderManagement(
                self.identity, self.physical_registry
            ),
            ai_providers=self.ai_management,
            audit=self.audit,
        )

    def close(self) -> None:
        self.identity_store.close()


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.sanova = WebContext()
        try:
            yield
        finally:
            application.state.sanova.close()

    app = FastAPI(title="Sanova", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def force_https_scheme(request: Request, call_next):
        if _bool_env("SANOVA_FORCE_HTTPS", False):
            request.scope["scheme"] = "https"
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.state.sanova = None

    jinja = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
    )

    def locale_for(request: Request) -> str:
        cookie = request.cookies.get("sanova_locale")
        return normalize_locale(cookie) if cookie else browser_locale(request.headers.get("accept-language"))

    def theme_for(request: Request) -> str:
        theme = request.cookies.get("sanova_theme", "light")
        return theme if theme in {"light", "dark"} else "light"

    def render(request: Request, template: str, status_code: int = 200, **context):
        locale = locale_for(request)
        user = current_user(request)
        base = {
            "request": request,
            "locale": locale,
            "theme": theme_for(request),
            "user": user,
            "t": lambda key, **values: translate(locale, key, **values),
            "url_for": request.url_for,
        }
        base.update(context)
        return HTMLResponse(jinja.get_template(template).render(**base), status_code=status_code)

    def current_user(request: Request):
        token = request.cookies.get("sanova_session")
        return app.state.sanova.identity.current_user(token) if token else None

    def safe_redirect_path(value: str | None, default: str = "/app") -> str:
        candidate = (value or "").strip()
        if not candidate or "\\" in candidate:
            return default
        parsed = urlsplit(candidate)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
            return default
        return candidate

    def require_user(request: Request):
        user = current_user(request)
        if user is None:
            return None, RedirectResponse(f"/login?next={quote(str(request.url.path))}", status_code=303)
        return user, None

    def _super_admin_access_signature(issued_at: str, access_code: str) -> str:
        key = hashlib.sha256(access_code.encode("utf-8")).digest()
        message = f"access|{issued_at}".encode("utf-8")
        return hmac.new(key, message, hashlib.sha256).hexdigest()

    def _super_admin_access_valid(request: Request) -> bool:
        gate = request.cookies.get("sanova_super_admin_access")
        access_code = super_admin_access_code()
        if not gate or not access_code:
            return False
        try:
            issued_at, signature = gate.split(".", 1)
            issued = int(issued_at)
        except (TypeError, ValueError):
            return False
        now = int(time.time())
        if issued > now or now - issued > 600:
            return False
        expected = _super_admin_access_signature(issued_at, access_code)
        return hmac.compare_digest(signature, expected)

    def _super_admin_gate_signature(session_token: str, issued_at: str, access_code: str) -> str:
        key = hashlib.sha256(access_code.encode("utf-8")).digest()
        message = f"{session_token}|{issued_at}".encode("utf-8")
        return hmac.new(key, message, hashlib.sha256).hexdigest()

    def _super_admin_gate_valid(request: Request) -> bool:
        token = request.cookies.get("sanova_session")
        gate = request.cookies.get("sanova_super_admin_gate")
        access_code = super_admin_access_code()
        if not token or not gate or not access_code:
            return False
        try:
            issued_at, signature = gate.split(".", 1)
            issued = int(issued_at)
        except (TypeError, ValueError):
            return False
        now = int(time.time())
        if issued > now or now - issued > 3600:
            return False
        expected = _super_admin_gate_signature(token, issued_at, access_code)
        return hmac.compare_digest(signature, expected)

    def require_super_admin(request: Request, permission: Permission):
        if not _super_admin_gate_valid(request):
            if _super_admin_access_valid(request):
                return None, render(request, "super_admin/login.html", error=None, status_code=401)
            return None, render(request, "super_admin/gate.html", error=None, status_code=401)
        user, redirect = require_user(request)
        if redirect:
            return None, redirect
        if not app.state.sanova.identity.authorization.has_permission(user, permission):
            return None, render(request, "super_admin/denied.html", status_code=403)
        return user, None

    def session_token(request: Request) -> str | None:
        return request.cookies.get("sanova_session")

    def provider_factory(name: str):
        if name == "mock":
            return MockProvider
        if name == "prodigi":
            enabled = _bool_env("SANOVA_SANDBOX_HTTP_ENABLED", False)
            return lambda: ProdigiSandboxAdapter(simulation=not enabled)
        if name == "cloudprinter":
            enabled = _bool_env("SANOVA_SANDBOX_HTTP_ENABLED", False)
            return lambda: CloudprinterSandboxAdapter(simulation=not enabled)
        raise ValueError(f"unsupported provider factory: {name}")

    def google_oauth_available() -> bool:
        if os.getenv("SANOVA_OAUTH_PROVIDER", "mock").strip().lower() != "google":
            return False
        try:
            config = app.state.sanova.oauth_registry.get("google").config
        except Exception:
            return False
        return bool(config.client_id and config.redirect_uri)

    def set_session_cookie(response: RedirectResponse, token: str) -> None:
        response.set_cookie(
            "sanova_session", token, httponly=True,
            secure=_bool_env("SANOVA_COOKIE_SECURE", False),
            samesite="lax", path="/",
        )

    @app.get("/health", response_class=JSONResponse)
    async def health():
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse, name="public_home")
    async def public_home(request: Request):
        return render(request, "public/index.html")

    @app.get("/privacy", response_class=HTMLResponse)
    async def privacy(request: Request):
        return render(request, "public/privacy.html")

    @app.get("/terms", response_class=HTMLResponse)
    async def terms(request: Request):
        return render(request, "public/terms.html")

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if current_user(request):
            return RedirectResponse("/app", status_code=303)
        return render(request, "public/login.html", error=None, google_oauth=google_oauth_available())

    @app.post("/login")
    async def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/app")):
        try:
            token = app.state.sanova.identity.authenticate(email, password)
        except PermissionError:
            return render(request, "public/login.html", error=translate(locale_for(request), "auth.invalid"), google_oauth=google_oauth_available())
        response = RedirectResponse(safe_redirect_path(next), status_code=303)
        response.set_cookie("sanova_session", token, httponly=True, secure=_bool_env("SANOVA_COOKIE_SECURE", False), samesite="lax", path="/")
        return response

    @app.get("/signup", response_class=HTMLResponse)
    async def signup_page(request: Request):
        return render(request, "public/signup.html", error=None, google_oauth=google_oauth_available())

    @app.post("/signup")
    async def signup(request: Request, email: str = Form(...), password: str = Form(...)):
        try:
            user, code = app.state.sanova.identity.register_pending(email, password)
            provider_name = os.getenv("SANOVA_EMAIL_PROVIDER", "mock").strip().lower()
            provider = app.state.sanova.email_registry.get(provider_name)
            provider.send(EmailMessage(
                to=user.email,
                subject="Verify your Sanova email",
                text=f"Your Sanova verification code is {code}. It expires in 10 minutes.",
                html=f"<p>Your Sanova verification code is <strong>{code}</strong>.</p><p>It expires in 10 minutes.</p>",
                from_name="Sanova",
            ))
        except ValueError as exc:
            key = "auth.email_exists" if "already registered" in str(exc) else "auth.password_policy"
            return render(request, "public/signup.html", error=translate(locale_for(request), key), google_oauth=google_oauth_available())
        except Exception as exc:
            return render(request, "public/signup.html", error=str(exc), google_oauth=google_oauth_available())
        return RedirectResponse("/verify-email?email=" + quote(user.email), status_code=303)

    @app.get("/verify-email", response_class=HTMLResponse)
    async def verify_email_page(request: Request):
        return render(request, "public/verify_email.html", error=None)

    @app.post("/verify-email")
    async def verify_email(request: Request, email: str = Form(...), code: str = Form(...)):
        if not app.state.sanova.identity.verify_email_code(email, code):
            return render(request, "public/verify_email.html", error=translate(locale_for(request), "auth.verify_invalid"))
        return RedirectResponse("/login?verified=1", status_code=303)

    @app.post("/logout")
    async def logout(request: Request):
        token = request.cookies.get("sanova_session")
        if token:
            app.state.sanova.identity.logout(token)
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie("sanova_session", path="/")
        response.delete_cookie("sanova_super_admin_gate", path="/")
        response.delete_cookie("sanova_super_admin_access", path="/")
        return response

    @app.get("/app", response_class=HTMLResponse)
    async def dashboard(request: Request):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        runtime = runtime_readiness()
        deployment = deployment_readiness()
        events = app.state.sanova.audit.events()
        return render(request, "private/dashboard.html", runtime=runtime, deployment=deployment, audit_count=len(events))

    @app.get("/app/execute", response_class=HTMLResponse)
    async def execute_page(request: Request):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        providers = app.state.sanova.physical_registry.names(enabled_only=True)
        return render(request, "private/execute.html", providers=providers, result=None, error=None)

    @app.post("/app/execute", response_class=HTMLResponse)
    async def execute(
        request: Request,
        intent: str = Form(...),
        provider: str = Form("mock"),
    ):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        providers = app.state.sanova.physical_registry.names(enabled_only=True)
        try:
            if provider not in providers:
                raise ValueError(f"unsupported provider: {provider}")
            intent = f"{intent.strip()} via {provider}"
            result = app.state.sanova.application.execute_intent(intent, owner_id=user.id)
            app.state.sanova.audit.append("web_execution_requested", result.task_id, metadata={"actor_id": user.id})
            return render(request, "private/execute.html", providers=providers, result=result, error=None)
        except Exception as exc:
            return render(request, "private/execute.html", providers=providers, result=None, error=str(exc))

    def task_records(user_id: str):
        root = app.state.sanova.execution_store.root
        if root is None:
            return []
        records = []
        for path in sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if record.get("task", {}).get("owner_id") == user_id:
                    records.append(record)
            except (OSError, ValueError):
                continue
        return records

    @app.get("/app/ai", response_class=HTMLResponse)
    async def ai_page(request: Request):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        providers = {name: [{"provider": item.provider, "model": item.model, "label": item.label} for item in app.state.sanova.ai_providers.models(name)] for name in app.state.sanova.ai_providers.names()}
        preference = app.state.sanova.identity_store.get_ai_preferences(user.id)
        provider = preference["provider"] if preference and preference["provider"] in providers else next(iter(providers))
        models = providers[provider]
        model = preference["model"] if preference and any(item["model"] == preference["model"] for item in models) else (models[0]["model"] if models else "")
        conversation_id = request.query_params.get("conversation")
        record = app.state.sanova.ai_store.get(conversation_id) if conversation_id else None
        if record and record.get("user_id") != user.id:
            record = None
            conversation_id = None
        return render(request, "private/ai.html", providers=providers, provider=provider, model=model, conversation_id=conversation_id, record=record, result=None, error=None)

    @app.post("/app/ai/chat", response_class=HTMLResponse)
    async def ai_chat(request: Request, message: str = Form(...), provider: str = Form(...), model: str = Form(...), conversation_id: str = Form("")):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        try:
            if not app.state.sanova.ai_providers.has_model(provider, model):
                raise ValueError("selected AI provider/model is not available")
            app.state.sanova.identity_store.save_ai_preferences(user.id, provider, model)
            turn = app.state.sanova.ai_agent.chat(user_id=user.id, conversation_id=conversation_id or None, provider=provider, model=model, message=message)
            record = app.state.sanova.ai_store.get(turn.conversation_id)
            providers = {name: [{"provider": item.provider, "model": item.model, "label": item.label} for item in app.state.sanova.ai_providers.models(name)] for name in app.state.sanova.ai_providers.names()}
            return render(request, "private/ai.html", providers=providers, provider=provider, model=model, conversation_id=turn.conversation_id, record=record, result=turn, error=turn.error)
        except Exception as exc:
            providers = {name: [{"provider": item.provider, "model": item.model, "label": item.label} for item in app.state.sanova.ai_providers.models(name)] for name in app.state.sanova.ai_providers.names()}
            return render(request, "private/ai.html", providers=providers, provider=provider, model=model, conversation_id=conversation_id, record=None, result=None, error=str(exc))

    @app.post("/app/ai/approve", response_class=HTMLResponse)
    async def ai_approve(request: Request, conversation_id: str = Form(...)):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        try:
            if not app.state.sanova.identity.authorization.has_permission(user, Permission.EXECUTE):
                raise PermissionError("execution permission required")
            proposal = app.state.sanova.ai_agent.approve(user_id=user.id, conversation_id=conversation_id)
            if proposal["tool"].startswith("google_"):
                result = app.state.sanova.ai_tools.call(
                    proposal["tool"], proposal["data"], context={"user_id": user.id}, approved=True
                )
                app.state.sanova.ai_agent.complete_approval(user_id=user.id, conversation_id=conversation_id)
                app.state.sanova.audit.append(
                    "ai_google_action_approved", conversation_id,
                    metadata={"actor_id": user.id, "tool": proposal["tool"]},
                )
                return RedirectResponse(f"/app/ai?conversation={quote(conversation_id)}&executed=1", status_code=303)
            app.state.sanova.identity.authorization.require_consent(user, "physical-action", "v1")
            data = proposal["data"]
            spec = PhysicalTaskSpec(**data)
            result = app.state.sanova.application.execute_spec(spec)
            app.state.sanova.ai_agent.complete_approval(user_id=user.id, conversation_id=conversation_id)
            app.state.sanova.audit.append("ai_action_approved", result.task_id, metadata={"actor_id": user.id, "conversation_id": conversation_id, "provider": result.provider})
            return RedirectResponse(f"/app/ai?conversation={quote(conversation_id)}&executed=1&task={quote(result.task_id)}", status_code=303)
        except Exception as exc:
            try:
                app.state.sanova.ai_agent.restore_approval(user_id=user.id, conversation_id=conversation_id)
            except Exception:
                pass
            return RedirectResponse(f"/app/ai?conversation={quote(conversation_id)}&error={quote(str(exc))}", status_code=303)

    @app.post("/app/ai/reject")
    async def ai_reject(request: Request, conversation_id: str = Form(...)):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        try:
            app.state.sanova.ai_agent.reject(user_id=user.id, conversation_id=conversation_id)
            app.state.sanova.audit.append("ai_action_rejected", conversation_id, metadata={"actor_id": user.id})
        except Exception:
            pass
        return RedirectResponse(f"/app/ai?conversation={quote(conversation_id)}", status_code=303)

    @app.get("/app/tasks", response_class=HTMLResponse)
    async def tasks(request: Request):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        return render(request, "private/tasks.html", records=task_records(user.id))

    @app.get("/app/integrations", response_class=HTMLResponse)
    async def integrations(request: Request):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        return render(
            request,
            "private/integrations.html",
            physical=app.state.sanova.physical_registry.names(),
            physical_enabled=app.state.sanova.physical_registry.names(enabled_only=True),
            email=os.getenv("SANOVA_EMAIL_PROVIDER", "mock"),
            oauth=os.getenv("SANOVA_OAUTH_PROVIDER", "mock"),
            webhook="available",
            email_result=request.query_params.get("email_result"),
            oauth_result=request.query_params.get("oauth_result"),
            oauth_error=request.query_params.get("oauth_error"),
            google_connected=app.state.sanova.google.connected(user.id),
        )

    @app.post("/app/integrations/email/test")
    async def integrations_email_test(request: Request, recipient: str = Form(...)):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        try:
            provider_name = os.getenv("SANOVA_EMAIL_PROVIDER", "mock").strip().lower()
            provider = app.state.sanova.email_registry.get(provider_name)
            result = provider.send(EmailMessage(
                to=recipient.strip(),
                subject="Sanova integration test",
                text="Sanova email integration test succeeded.",
                from_name="Sanova",
            ))
            message = f"{result.provider}: {result.message}"
            return RedirectResponse("/app/integrations?email_result=" + quote(message), status_code=303)
        except Exception as exc:
            return RedirectResponse("/app/integrations?email_result=" + quote(str(exc)), status_code=303)

    @app.get("/oauth/google/start")
    async def oauth_google_start(request: Request, mode: str = "connect", next: str = "/app"):
        provider_name = os.getenv("SANOVA_OAUTH_PROVIDER", "mock").strip().lower()
        if provider_name != "google":
            return RedirectResponse("/login?oauth_error=" + quote("Google OAuth is not configured"), status_code=303)
        user = current_user(request)
        if mode == "connect" and user is None:
            return RedirectResponse("/login?next=/app/integrations", status_code=303)
        if mode not in {"login", "signup", "connect"}:
            mode = "login"
        provider = app.state.sanova.oauth_registry.get("google")
        state, verifier = app.state.sanova.oauth_states.issue(
            user.id if user and mode == "connect" else None,
            provider_name,
            purpose=mode,
            next_path=next if next.startswith("/") else "/app",
        )
        scopes = provider.config.scopes if mode == "connect" else ("openid", "email", "profile")
        authorization = provider.authorization_url(state, scopes=scopes, code_verifier=verifier)
        return RedirectResponse(authorization.url, status_code=303)

    @app.get("/oauth/callback")
    async def oauth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
        if error or not code or not state:
            target = "/app/integrations" if current_user(request) else "/login"
            return RedirectResponse(target + "?oauth_error=" + quote(error or "OAuth callback was incomplete"), status_code=303)
        provider_name = os.getenv("SANOVA_OAUTH_PROVIDER", "mock").strip().lower()
        provider = app.state.sanova.oauth_registry.get(provider_name)
        user = current_user(request)
        record = app.state.sanova.oauth_states.consume_record(
            state, user.id if user else None, provider_name
        )
        if record is None:
            target = "/app/integrations" if user else "/login"
            return RedirectResponse(target + "?oauth_error=" + quote("Invalid or expired OAuth state"), status_code=303)
        try:
            token = provider.exchange_code(code, code_verifier=record["verifier"])
            identity = provider.identity_from_userinfo(token.access_token) if hasattr(provider, "identity_from_userinfo") else None
            if identity is None or not identity.email:
                raise RuntimeError("Google did not return a verified email identity")

            if record["purpose"] in {"login", "signup"}:
                existing = app.state.sanova.identity.store.get_user_by_email(identity.email)
                if existing is None:
                    import secrets
                    existing = app.state.sanova.identity.register(identity.email, secrets.token_urlsafe(32))
                if not existing.active:
                    raise PermissionError("account is inactive")
                session = app.state.sanova.identity.authenticate_oauth(identity.email)
                response = RedirectResponse(record["next_path"] or "/app", status_code=303)
                set_session_cookie(response, session)
                return response

            if user is None:
                return RedirectResponse("/login?oauth_error=" + quote("Authentication required"), status_code=303)
            if provider_name == "google":
                scopes = tuple(filter(None, (token.scope or " ").replace(",", " ").split()))
                app.state.sanova.connected_accounts.save(
                    user_id=user.id,
                    provider="google",
                    external_subject=identity.subject,
                    email=identity.email,
                    access_token=token.access_token,
                    refresh_token=token.refresh_token,
                    token_type=token.token_type,
                    expires_in=token.expires_in,
                    scopes=scopes,
                )
            label = identity.email
            return RedirectResponse("/app/integrations?oauth_result=" + quote(f"Connected {provider_name}: {label}"), status_code=303)
        except Exception as exc:
            target = "/app/integrations" if user else "/login"
            return RedirectResponse(target + "?oauth_error=" + quote(str(exc)), status_code=303)

    @app.post("/app/integrations/google/disconnect")
    async def integrations_google_disconnect(request: Request):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        account = app.state.sanova.connected_accounts.get(user.id, "google")
        if account:
            try:
                app.state.sanova.oauth_registry.get("google").revoke(account.refresh_token or account.access_token)
            except Exception:
                pass
            app.state.sanova.connected_accounts.delete(user.id, "google")
        return RedirectResponse("/app/integrations?oauth_result=" + quote("Google disconnected"), status_code=303)

    @app.get("/app/settings", response_class=HTMLResponse)
    async def settings(request: Request):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        has_consent = app.state.sanova.identity.authorization.has_consent(user, "physical-action", "v1")
        ai_preference = app.state.sanova.identity_store.get_ai_preferences(user.id)
        ai_providers = {name: [{"provider": item.provider, "model": item.model, "label": item.label} for item in app.state.sanova.ai_providers.models(name)] for name in app.state.sanova.ai_providers.names()}
        return render(request, "private/account/settings.html", has_consent=has_consent, saved=request.query_params.get("saved") == "1", ai_preference=ai_preference, ai_providers=ai_providers)

    @app.post("/app/settings")
    async def save_settings(request: Request, locale: str = Form(...), theme: str = Form(...), ai_provider: str = Form(""), ai_model: str = Form("")):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        if ai_provider and ai_model:
            if not app.state.sanova.ai_providers.has_model(ai_provider, ai_model):
                return RedirectResponse("/app/settings?saved=0", status_code=303)
            app.state.sanova.identity_store.save_ai_preferences(user.id, ai_provider, ai_model)
        response = RedirectResponse("/app/settings?saved=1", status_code=303)
        response.set_cookie("sanova_locale", normalize_locale(locale), httponly=False, secure=_bool_env("SANOVA_COOKIE_SECURE", False), samesite="lax", path="/")
        response.set_cookie("sanova_theme", theme if theme in {"light", "dark"} else "light", httponly=False, secure=_bool_env("SANOVA_COOKIE_SECURE", False), samesite="lax", path="/")
        return response

    @app.post("/app/settings/consent")
    async def consent(request: Request, action: str = Form(...)):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        if action == "grant":
            app.state.sanova.identity.authorization.grant_consent(user, "physical-action", "v1")
        elif action == "revoke":
            app.state.sanova.identity.authorization.revoke_consent(user, "physical-action")
        return RedirectResponse("/app/settings", status_code=303)

    @app.get("/super-admin", response_class=HTMLResponse)
    async def super_admin_gate(request: Request):
        if not _super_admin_gate_valid(request):
            if _super_admin_access_valid(request):
                return render(request, "super_admin/login.html", error=None, status_code=401)
            return render(request, "super_admin/gate.html", error=None, status_code=401)
        user, redirect = require_super_admin(request, Permission.MANAGE_USERS)
        if redirect:
            return redirect
        users = app.state.sanova.management.list_users(request.cookies.get("sanova_session"))
        providers = app.state.sanova.management.list_providers(request.cookies.get("sanova_session"))
        enabled = app.state.sanova.management.list_providers(request.cookies.get("sanova_session"), enabled_only=True)
        events = app.state.sanova.audit.events()
        ai_providers = app.state.sanova.management.list_ai_providers(request.cookies.get("sanova_session"))
        return render(
            request,
            "super_admin/index.html",
            users=users,
            providers=providers,
            enabled=enabled,
            ai_providers=ai_providers,
            events=events,
            audit_valid=app.state.sanova.audit.verify(),
        )

    @app.post("/super-admin/access")
    async def super_admin_access(request: Request, access_code: str = Form(...)):
        configured_code = super_admin_access_code()
        if not configured_code:
            return render(request, "super_admin/gate.html", error="Super Admin access is not configured.", status_code=503)
        if not hmac.compare_digest(access_code, configured_code):
            return render(request, "super_admin/gate.html", error="Invalid access code.", status_code=401)
        issued_at = str(int(time.time()))
        access_gate = f"{issued_at}.{_super_admin_access_signature(issued_at, configured_code)}"
        response = RedirectResponse("/super-admin/login", status_code=303)
        response.set_cookie("sanova_super_admin_access", access_gate, httponly=True, secure=_bool_env("SANOVA_COOKIE_SECURE", False), samesite="lax", path="/", max_age=600)
        return response

    @app.get("/super-admin/login", response_class=HTMLResponse)
    async def super_admin_login_page(request: Request):
        if not _super_admin_access_valid(request):
            return RedirectResponse("/super-admin", status_code=303)
        if _super_admin_gate_valid(request):
            return RedirectResponse("/super-admin", status_code=303)
        return render(request, "super_admin/login.html", error=None, status_code=401)

    @app.post("/super-admin/login")
    async def super_admin_login(request: Request, email: str = Form(...), password: str = Form(...)):
        if not _super_admin_access_valid(request):
            return RedirectResponse("/super-admin", status_code=303)
        configured_code = super_admin_access_code()
        try:
            token = app.state.sanova.identity.authenticate(email, password)
        except PermissionError:
            return render(request, "super_admin/login.html", error="Invalid credentials.", status_code=401)
        user = app.state.sanova.identity.current_user(token)
        if user is None or not app.state.sanova.identity.authorization.has_permission(user, Permission.MANAGE_USERS):
            app.state.sanova.identity.logout(token)
            return render(request, "super_admin/denied.html", status_code=403)
        issued_at = str(int(time.time()))
        gate = f"{issued_at}.{_super_admin_gate_signature(token, issued_at, configured_code)}"
        response = RedirectResponse("/super-admin", status_code=303)
        set_session_cookie(response, token)
        response.set_cookie(
            "sanova_super_admin_gate",
            gate,
            httponly=True,
            secure=_bool_env("SANOVA_COOKIE_SECURE", False),
            samesite="lax",
            path="/",
            max_age=3600,
        )
        response.delete_cookie("sanova_super_admin_access", path="/")
        return response

    @app.get("/super-admin/users/{user_id}", response_class=HTMLResponse)
    async def admin_user_detail(request: Request, user_id: str):
        user, redirect = require_super_admin(request, Permission.MANAGE_USERS)
        if redirect:
            return redirect
        item = app.state.sanova.management.get_user(session_token(request), user_id)
        if item is None:
            return render(request, "public/error.html", message=translate(locale_for(request), "errors.not_found"), status_code=404)
        return render(request, "super_admin/user.html", item=item)

    @app.post("/super-admin/users/{user_id}/active")
    async def admin_user_active(request: Request, user_id: str, active: str = Form(...)):
        user, redirect = require_super_admin(request, Permission.MANAGE_USERS)
        if redirect:
            return redirect
        try:
            app.state.sanova.management.set_user_active(request.cookies.get("sanova_session"), user_id, active == "true")
        except Exception:
            pass
        return RedirectResponse("/super-admin", status_code=303)

    @app.post("/super-admin/users/{user_id}/role")
    async def admin_user_role(request: Request, user_id: str, action: str = Form(...)):
        user, redirect = require_super_admin(request, Permission.MANAGE_ADMINS)
        if redirect:
            return redirect
        try:
            if action == "grant":
                app.state.sanova.management.grant_admin(request.cookies.get("sanova_session"), user_id)
            elif action == "revoke":
                app.state.sanova.management.revoke_admin(request.cookies.get("sanova_session"), user_id)
        except Exception:
            pass
        return RedirectResponse("/super-admin", status_code=303)

    @app.post("/super-admin/ai/{name}/connect")
    async def admin_ai_connect(request: Request, name: str, credential: str = Form(...), base_url: str = Form("")):
        user, redirect = require_super_admin(request, Permission.MANAGE_PROVIDERS)
        if redirect:
            return redirect
        try:
            app.state.sanova.management.connect_ai_provider(
                request.cookies.get("sanova_session"), name, credential, base_url=base_url or None
            )
        except Exception:
            request.app.state.sanova.audit.append(
                "ai_provider_connect_failed", name, outcome="error",
                metadata={"actor_id": user.id, "actor_role": user.role},
            )
        return RedirectResponse("/super-admin", status_code=303)

    @app.post("/super-admin/ai/{name}/test")
    async def admin_ai_test(request: Request, name: str):
        user, redirect = require_super_admin(request, Permission.MANAGE_PROVIDERS)
        if redirect:
            return redirect
        try:
            app.state.sanova.management.test_ai_provider(request.cookies.get("sanova_session"), name)
        except Exception:
            app.state.sanova.audit.append("ai_provider_test_failed", name, outcome="error", metadata={"actor_id": user.id, "actor_role": user.role})
        return RedirectResponse("/super-admin", status_code=303)

    @app.post("/super-admin/ai/{name}/enable")
    async def admin_ai_enable(request: Request, name: str):
        user, redirect = require_super_admin(request, Permission.MANAGE_PROVIDERS)
        if redirect:
            return redirect
        try:
            app.state.sanova.management.enable_ai_provider(request.cookies.get("sanova_session"), name)
        except Exception:
            pass
        return RedirectResponse("/super-admin", status_code=303)

    @app.post("/super-admin/ai/{name}/disable")
    async def admin_ai_disable(request: Request, name: str):
        user, redirect = require_super_admin(request, Permission.MANAGE_PROVIDERS)
        if redirect:
            return redirect
        try:
            app.state.sanova.management.disable_ai_provider(request.cookies.get("sanova_session"), name)
        except Exception:
            pass
        return RedirectResponse("/super-admin", status_code=303)

    @app.post("/super-admin/ai/{name}/replace")
    async def admin_ai_replace(request: Request, name: str, credential: str = Form(...)):
        user, redirect = require_super_admin(request, Permission.MANAGE_PROVIDERS)
        if redirect:
            return redirect
        try:
            app.state.sanova.management.replace_ai_credential(request.cookies.get("sanova_session"), name, credential)
        except Exception:
            pass
        return RedirectResponse("/super-admin", status_code=303)

    @app.post("/super-admin/ai/{name}/revoke")
    async def admin_ai_revoke(request: Request, name: str):
        user, redirect = require_super_admin(request, Permission.MANAGE_PROVIDERS)
        if redirect:
            return redirect
        try:
            app.state.sanova.management.revoke_ai_provider(request.cookies.get("sanova_session"), name)
        except Exception:
            pass
        return RedirectResponse("/super-admin", status_code=303)

    @app.post("/super-admin/ai/{name}/model")
    async def admin_ai_model(request: Request, name: str, model: str = Form(...)):
        user, redirect = require_super_admin(request, Permission.MANAGE_PROVIDERS)
        if redirect:
            return redirect
        try:
            app.state.sanova.management.set_ai_provider_model(request.cookies.get("sanova_session"), name, model)
        except Exception:
            pass
        return RedirectResponse("/super-admin", status_code=303)

    @app.post("/super-admin/providers/register")
    async def admin_provider_register(request: Request, name: str = Form(...)):
        user, redirect = require_super_admin(request, Permission.MANAGE_PROVIDERS)
        if redirect:
            return redirect
        try:
            app.state.sanova.management.register_provider(session_token(request), name, provider_factory(name), enabled=True)
        except Exception:
            pass
        return RedirectResponse("/super-admin", status_code=303)

    @app.post("/super-admin/providers/{name}")
    async def admin_provider(request: Request, name: str, action: str = Form(...)):
        user, redirect = require_super_admin(request, Permission.MANAGE_PROVIDERS)
        if redirect:
            return redirect
        try:
            if action == "enable":
                app.state.sanova.management.enable_provider(request.cookies.get("sanova_session"), name)
            elif action == "disable":
                app.state.sanova.management.disable_provider(request.cookies.get("sanova_session"), name)
            elif action == "remove":
                app.state.sanova.management.remove_provider(request.cookies.get("sanova_session"), name)
            elif action == "register":
                app.state.sanova.management.register_provider(request.cookies.get("sanova_session"), name, provider_factory(name), enabled=True)
        except Exception:
            pass
        return RedirectResponse("/super-admin", status_code=303)

    @app.get("/app/simulate", response_class=HTMLResponse)
    async def simulate_page(request: Request):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        providers = app.state.sanova.physical_registry.names(enabled_only=True)
        return render(request, "private/simulate.html", providers=providers, result=None, error=None)

    @app.post("/app/simulate", response_class=HTMLResponse)
    async def simulate(request: Request, intent: str = Form(...), provider: str = Form("mock")):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        providers = app.state.sanova.physical_registry.names(enabled_only=True)
        try:
            parsed = app.state.sanova.application.parser.parse(f"{intent.strip()} via {provider}")
            spec = PhysicalTaskSpec(
                intent=parsed.intent, action=parsed.action, product=parsed.product,
                asset=parsed.asset, destination=parsed.destination, quantity=parsed.quantity, provider=provider,
            )
            simulation = EndToEndSimulation(engine=app.state.sanova.engine)
            task, verification = simulation.run(spec, statuses=("processing", "fulfillment", "shipped", "completed"))
            task.owner_id = user.id
            result = {"task_id": task.id, "state": task.state.value, "verified": verification.verified, "message": verification.message, "provider": provider}
            app.state.sanova.execution_store.put(task, app.state.sanova.execution_store.result_from_dict({"accepted": True, "status": task.state.value, "external_id": task.external_id, "message": verification.message}), "completed")
            app.state.sanova.audit.append("e2e_simulation_completed", task.id, state=task.state.value, provider=provider, metadata={"actor_id": user.id, "verified": verification.verified})
            return render(request, "private/simulate.html", providers=providers, result=result, error=None)
        except Exception as exc:
            return render(request, "private/simulate.html", providers=providers, result=None, error=str(exc))

    @app.post("/app/tasks/{task_id}/webhook")
    async def task_webhook(request: Request, task_id: str, status: str = Form(...)):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        record = app.state.sanova.execution_store.get(task_id)
        if not record:
            return RedirectResponse("/app/tasks?webhook_error=" + quote("Task not found"), status_code=303)
        stored = record["task"]
        if stored.get("owner_id") != user.id:
            return RedirectResponse("/app/tasks?webhook_error=" + quote("Task not found"), status_code=303)
        task = PhysicalTask(intent=stored["intent"], provider=stored.get("provider"), id=stored["id"], state=TaskState(stored["state"]), external_id=stored.get("external_id"), action=stored.get("action"), product=stored.get("product"), asset=stored.get("asset"), destination=stored.get("destination"), quantity=stored.get("quantity", 1), owner_id=stored.get("owner_id"))
        provider_name = stored.get("provider") or "mock"
        provider = app.state.sanova.physical_registry.get(provider_name)
        try:
            task = handle_provider_webhook(task, provider, status, audit=app.state.sanova.audit)
            result = app.state.sanova.execution_store.result_from_dict(record.get("result"))
            app.state.sanova.execution_store.put(task, result, "completed")
            app.state.sanova.audit.append("webhook_ui_processed", task.id, state=task.state.value, provider=provider_name, metadata={"actor_id": user.id, "raw_status": status})
            return RedirectResponse("/app/tasks?webhook_status=" + quote(task.state.value), status_code=303)
        except Exception as exc:
            return RedirectResponse("/app/tasks?webhook_error=" + quote(str(exc)), status_code=303)

    @app.get("/app/readiness", response_class=HTMLResponse)
    async def readiness(request: Request):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        return render(request, "private/readiness.html", runtime=runtime_readiness(), deployment=deployment_readiness())

    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        return render(request, "public/error.html", message=translate(locale_for(request), "errors.not_found"))

    return app


app = create_app()
