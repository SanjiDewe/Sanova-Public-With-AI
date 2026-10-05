from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import User


class IdentityStore:
    """Persistence for identity data.

    Local/test runs use SQLite. Deployment can use PostgreSQL by supplying
    DATABASE_URL (for example, a Neon PostgreSQL connection string).
    SANOVA_IDENTITY_DB remains an explicit local/test override.
    """

    def __init__(self, path: str | None = None, database_url: str | None = None):
        explicit_path = path if path is not None else os.getenv("SANOVA_IDENTITY_DB")
        url = database_url or (None if explicit_path else os.getenv("DATABASE_URL"))

        if url:
            self._backend = "postgres"
            self._database_url = self._normalize_postgres_url(url)
            self._connect_postgres()
            self._initialize_postgres()
        else:
            environment = os.getenv("SANOVA_ENVIRONMENT", "local").strip().lower()
            if explicit_path is None and environment not in {"local", "test", "development"}:
                raise RuntimeError(
                    "DATABASE_URL is required outside local/test/development; "
                    "refusing to use SQLite identity storage in deployment"
                )
            self._backend = "sqlite"
            sqlite_path = explicit_path if explicit_path is not None else ":memory:"
            self._conn = sqlite3.connect(sqlite_path)
            self._conn.row_factory = sqlite3.Row
            self._initialize_sqlite()

    @staticmethod
    def _normalize_postgres_url(url: str) -> str:
        """Ensure a remote PostgreSQL deployment uses TLS unless explicitly configured."""
        parts = urlsplit(url)
        if parts.scheme not in {"postgresql", "postgres"}:
            raise ValueError("DATABASE_URL must be a PostgreSQL connection URL")
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.setdefault("sslmode", "require")
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def _initialize_sqlite(self) -> None:
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revoked INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS consents (
            user_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            version TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, scope)
        );
        CREATE TABLE IF NOT EXISTS email_verifications (
            user_id TEXT PRIMARY KEY,
            code_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ai_preferences (
            user_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ai_provider_configs (
            name TEXT PRIMARY KEY, label TEXT NOT NULL, base_url TEXT NOT NULL, credential TEXT,
            models TEXT NOT NULL DEFAULT '[]', selected_model TEXT, enabled INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'not_configured', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS connected_accounts (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider TEXT NOT NULL, external_subject TEXT, email TEXT, access_token TEXT NOT NULL,
            refresh_token TEXT, token_type TEXT NOT NULL DEFAULT 'Bearer', expires_at TEXT,
            scopes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, provider)
        );
        CREATE TABLE IF NOT EXISTS oauth_states (
            state_hash TEXT PRIMARY KEY, user_id TEXT, provider TEXT NOT NULL,
            verifier TEXT NOT NULL, purpose TEXT NOT NULL, next_path TEXT NOT NULL,
            expires_at REAL NOT NULL
        );
        """)
        self._conn.commit()

    def _initialize_postgres(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revoked BOOLEAN NOT NULL DEFAULT FALSE
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS consents (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                scope TEXT NOT NULL,
                version TEXT NOT NULL,
                revoked BOOLEAN NOT NULL DEFAULT FALSE,
                PRIMARY KEY (user_id, scope)
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS email_verifications (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                code_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS ai_preferences (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                model TEXT NOT NULL
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS ai_provider_configs (
                name TEXT PRIMARY KEY, label TEXT NOT NULL, base_url TEXT NOT NULL, credential TEXT,
                models TEXT NOT NULL DEFAULT '[]', selected_model TEXT, enabled BOOLEAN NOT NULL DEFAULT FALSE,
                status TEXT NOT NULL DEFAULT 'not_configured', updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS connected_accounts (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider TEXT NOT NULL, external_subject TEXT, email TEXT, access_token TEXT NOT NULL,
                refresh_token TEXT, token_type TEXT NOT NULL DEFAULT 'Bearer', expires_at TIMESTAMPTZ,
                scopes TEXT NOT NULL DEFAULT '', updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, provider)
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS oauth_states (
                state_hash TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                provider TEXT NOT NULL, verifier TEXT NOT NULL, purpose TEXT NOT NULL,
                next_path TEXT NOT NULL, expires_at DOUBLE PRECISION NOT NULL
            )
            """)
        self._conn.commit()

    def _connect_postgres(self) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - packaging/configuration failure
            raise RuntimeError(
                "PostgreSQL identity storage requires the psycopg package"
            ) from exc
        self._conn = psycopg.connect(self._database_url, row_factory=dict_row)
        self._conn.autocommit = True

    def _reconnect_postgres(self) -> None:
        old_conn = getattr(self, "_conn", None)
        try:
            if old_conn is not None and not old_conn.closed:
                old_conn.close()
        except Exception:
            pass
        self._connect_postgres()
        self._initialize_postgres()

    def close(self):
        self._conn.close()

    def _execute(self, sql: str, params=()):
        if self._backend == "postgres":
            sql = sql.replace("?", "%s")
            try:
                return self._conn.cursor().execute(sql, params)
            except Exception as exc:
                import psycopg
                if not isinstance(exc, psycopg.OperationalError):
                    raise
                self._reconnect_postgres()
                return self._conn.cursor().execute(sql, params)
        return self._conn.execute(sql, params)

    def _commit(self) -> None:
        self._conn.commit()

    def _active_value(self, active: bool):
        return bool(active) if self._backend == "postgres" else int(active)

    def create_user(self, email, password_hash, role="user"):
        email = email.strip().lower()
        user = User(str(uuid.uuid4()), email, password_hash, role, True)
        try:
            self._execute(
                "INSERT INTO users(id,email,password_hash,role,active) VALUES(?,?,?,?,?)",
                (user.id, user.email, user.password_hash, user.role, self._active_value(True)),
            )
            self._commit()
        except (sqlite3.IntegrityError, Exception) as exc:
            if self._is_integrity_error(exc):
                self._rollback()
                raise ValueError("email already registered") from exc
            raise
        return user

    def _is_integrity_error(self, exc: Exception) -> bool:
        if isinstance(exc, sqlite3.IntegrityError):
            return True
        if self._backend == "postgres":
            try:
                import psycopg.errors
                return isinstance(exc, psycopg.errors.UniqueViolation)
            except ImportError:
                return False
        return False

    def _rollback(self) -> None:
        self._conn.rollback()

    def get_user_by_email(self, email):
        row = self._execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
        return self._row_user(row) if row else None

    def create_pending_user(self, email, password_hash, role="user"):
        email = email.strip().lower()
        user = User(str(uuid.uuid4()), email, password_hash, role, False)
        try:
            self._execute(
                "INSERT INTO users(id,email,password_hash,role,active) VALUES(?,?,?,?,?)",
                (user.id, user.email, user.password_hash, user.role, self._active_value(False)),
            )
            self._commit()
        except Exception as exc:
            if self._is_integrity_error(exc):
                self._rollback()
                raise ValueError("email already registered") from exc
            raise
        return user

    def save_email_verification(self, user_id, code_hash, expires_at):
        self._execute(
            "INSERT INTO email_verifications(user_id,code_hash,expires_at) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET code_hash=excluded.code_hash, expires_at=excluded.expires_at",
            (user_id, code_hash, expires_at),
        )
        self._commit()

    def get_email_verification(self, user_id):
        return self._execute(
            "SELECT code_hash, expires_at FROM email_verifications WHERE user_id=?", (user_id,)
        ).fetchone()

    def delete_email_verification(self, user_id):
        self._execute("DELETE FROM email_verifications WHERE user_id=?", (user_id,))
        self._commit()

    def get_user(self, user_id):
        row = self._execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return self._row_user(row) if row else None

    def list_users(self, *, active: bool | None = None):
        if active is None:
            rows = self._execute("SELECT * FROM users ORDER BY email").fetchall()
        else:
            rows = self._execute("SELECT * FROM users WHERE active=? ORDER BY email", (self._active_value(active),)).fetchall()
        return [self._row_user(row) for row in rows]

    def set_role(self, user_id, role):
        self._execute("UPDATE users SET role=? WHERE id=?", (str(role).strip().lower(), user_id))
        self._commit()

    def set_active(self, user_id, active):
        self._execute("UPDATE users SET active=? WHERE id=?", (self._active_value(active), user_id))
        self._commit()

    def create_session(self, user_id, token):
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        self._execute(
            "INSERT INTO sessions(id,user_id,token_hash) VALUES(?,?,?)",
            (str(uuid.uuid4()), user_id, token_hash),
        )
        self._commit()

    def get_user_by_token(self, token):
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        row = self._execute(
            """SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id
               WHERE s.token_hash=? AND s.revoked=?""",
            (token_hash, self._active_value(False)),
        ).fetchone()
        return self._row_user(row) if row else None

    def revoke_session(self, token):
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        self._execute("UPDATE sessions SET revoked=? WHERE token_hash=?", (self._active_value(True), token_hash))
        self._commit()

    def grant_consent(self, user_id, scope, version):
        self._execute(
            """INSERT INTO consents(user_id,scope,version,revoked) VALUES(?,?,?,?)
               ON CONFLICT(user_id,scope) DO UPDATE SET version=excluded.version, revoked=excluded.revoked""",
            (user_id, scope, version, self._active_value(False)),
        )
        self._commit()

    def revoke_consent(self, user_id, scope):
        self._execute("UPDATE consents SET revoked=? WHERE user_id=? AND scope=?", (self._active_value(True), user_id, scope))
        self._commit()

    def has_consent(self, user_id, scope, version):
        row = self._execute(
            "SELECT 1 FROM consents WHERE user_id=? AND scope=? AND version=? AND revoked=?",
            (user_id, scope, version, self._active_value(False)),
        ).fetchone()
        return row is not None


    def get_ai_preferences(self, user_id):
        row = self._execute(
            "SELECT provider, model FROM ai_preferences WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return {"provider": row["provider"], "model": row["model"]}

    def save_ai_preferences(self, user_id, provider, model):
        self._execute(
            """INSERT INTO ai_preferences(user_id, provider, model)
               VALUES(?,?,?)
               ON CONFLICT(user_id) DO UPDATE
               SET provider=excluded.provider, model=excluded.model""",
            (user_id, str(provider).strip().lower(), str(model).strip()),
        )
        self._commit()

    def get_ai_provider_config(self, name):
        row = self._execute("SELECT * FROM ai_provider_configs WHERE name=?", (str(name).strip().lower(),)).fetchone()
        return self._row_ai_provider(row) if row else None

    def list_ai_provider_configs(self):
        rows = self._execute("SELECT * FROM ai_provider_configs ORDER BY name").fetchall()
        return [self._row_ai_provider(row) for row in rows]

    def upsert_ai_provider_config(self, *, name, label, base_url, credential, models, selected_model, enabled, status):
        self._execute(
            """INSERT INTO ai_provider_configs(name,label,base_url,credential,models,selected_model,enabled,status)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET label=excluded.label, base_url=excluded.base_url,
               credential=excluded.credential, models=excluded.models, selected_model=excluded.selected_model,
               enabled=excluded.enabled, status=excluded.status, updated_at=CURRENT_TIMESTAMP""",
            (str(name).strip().lower(), str(label), str(base_url).rstrip("/"), credential, json.dumps(list(models)),
             selected_model, self._active_value(enabled), str(status)),
        )
        self._commit()

    def update_ai_provider_models(self, name, models, *, selected_model=None, status=None):
        current = self.get_ai_provider_config(name)
        if current is None:
            raise KeyError(name)
        self._execute(
            "UPDATE ai_provider_configs SET models=?, selected_model=?, status=COALESCE(?,status), updated_at=CURRENT_TIMESTAMP WHERE name=?",
            (json.dumps(list(models)), selected_model, status, str(name).strip().lower()),
        )
        self._commit()

    def set_ai_provider_state(self, name, *, enabled, status, models=None, selected_model=None):
        current = self.get_ai_provider_config(name)
        if current is None:
            raise KeyError(name)
        models = current.get("models", []) if models is None else models
        selected_model = current.get("selected_model") if selected_model is None else selected_model
        self._execute(
            "UPDATE ai_provider_configs SET enabled=?, status=?, models=?, selected_model=?, updated_at=CURRENT_TIMESTAMP WHERE name=?",
            (self._active_value(enabled), str(status), json.dumps(list(models)), selected_model, str(name).strip().lower()),
        )
        self._commit()

    def revoke_ai_provider_config(self, name):
        self._execute(
            "UPDATE ai_provider_configs SET credential=NULL, models=?, selected_model=NULL, enabled=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE name=?",
            (json.dumps([]), self._active_value(False), "revoked", str(name).strip().lower()),
        )
        self._commit()

    @staticmethod
    def _row_ai_provider(row):
        try:
            models = json.loads(row["models"] or "[]")
        except (TypeError, json.JSONDecodeError):
            models = []
        return {
            "name": row["name"], "label": row["label"], "base_url": row["base_url"],
            "credential": row["credential"], "models": tuple(models), "selected_model": row["selected_model"],
            "enabled": bool(row["enabled"]), "status": row["status"], "updated_at": row["updated_at"],
        }

    def save_oauth_state(self, *, state_hash, user_id, provider, verifier, purpose, next_path, expires_at):
        self._execute("DELETE FROM oauth_states WHERE expires_at<=?", (float(expires_at),))
        self._execute(
            "INSERT INTO oauth_states(state_hash,user_id,provider,verifier,purpose,next_path,expires_at) VALUES(?,?,?,?,?,?,?)",
            (state_hash, user_id, provider, verifier, purpose, next_path, float(expires_at)),
        )
        self._commit()

    def consume_oauth_state(self, *, state_hash, user_id, provider, now):
        row = self._execute(
            """DELETE FROM oauth_states
               WHERE state_hash=? AND provider=? AND expires_at>?
                 AND ((purpose='connect' AND user_id=?) OR (purpose IN ('login','signup') AND user_id IS NULL))
               RETURNING verifier, purpose, next_path""",
            (state_hash, provider, float(now), user_id),
        ).fetchone()
        self._commit()
        return row

    def save_connected_account(self, *, user_id, provider, external_subject, email, access_token,
                               refresh_token, token_type, expires_at, scopes):
        self._execute(
            """INSERT INTO connected_accounts(
                id,user_id,provider,external_subject,email,access_token,refresh_token,token_type,expires_at,scopes
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id,provider) DO UPDATE SET
                external_subject=excluded.external_subject, email=excluded.email, access_token=excluded.access_token,
                refresh_token=COALESCE(excluded.refresh_token, connected_accounts.refresh_token),
                token_type=excluded.token_type, expires_at=excluded.expires_at, scopes=excluded.scopes""",
            (str(uuid.uuid4()), user_id, provider, external_subject, email, access_token, refresh_token, token_type, expires_at, scopes),
        )
        self._commit()

    def get_connected_account(self, user_id, provider):
        return self._execute("SELECT * FROM connected_accounts WHERE user_id=? AND provider=?", (user_id, provider)).fetchone()

    def delete_connected_account(self, user_id, provider):
        self._execute("DELETE FROM connected_accounts WHERE user_id=? AND provider=?", (user_id, provider))
        self._commit()

    @staticmethod
    def _row_user(row):
        return User(row["id"], row["email"], row["password_hash"], row["role"], bool(row["active"]))
