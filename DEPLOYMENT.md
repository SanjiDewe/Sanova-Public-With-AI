# Sanova Deployment Readiness & Release Contract

## 1. Runtime boundary

Sanova is currently sandbox-only. Production activation and live physical execution remain hard-locked.

Required defaults:

```text
SANOVA_ENVIRONMENT=sandbox
SANOVA_LIVE_EXECUTION=false
SANOVA_SANDBOX_HTTP_ENABLED=false
```

Runtime components should resolve process configuration through `app.config.load_runtime_config()` or receive an explicit `RuntimeConfig`. Import-time compatibility constants are not the source of runtime safety decisions.

## 2. Pre-release verification

Run the complete suite from a clean environment:

```bash
pytest -q
python -m compileall app tests
```

The full suite must pass before an artifact is accepted.

## 3. Artifact hygiene

Build release/source ZIPs only through:

```bash
python scripts/build_artifact.py --output dist/sanova-source.zip
```

The builder excludes `.env`, bytecode, local runtime caches, and `.git`. A release artifact must not contain credentials or local execution state.

## 4. Secrets

Provider credentials are supplied through environment variables only. Never commit or distribute `.env` files or credentials. Use `.env.example` as the configuration reference.

If credentials have previously appeared in a local or shared artifact, rotate/revoke them at the relevant provider before reuse.

Do not place production provider credentials in a sandbox environment.

## 5. Provider lifecycle

Provider factories must remain lazy. Registration must not execute a factory. Router construction must not eagerly instantiate every enabled provider; a provider is instantiated when selected for an execution path.

## 6. Persistence and backup

The current engine uses file-backed JSON persistence. Before any operational production deployment, establish an external backup policy for the persistence directory and verify restoration on a separate copy. Source-control history is not an application-data backup.

## 7. Rollback

Rollback must restore the previously validated application artifact together with its compatible persistence backup. Do not automatically retry an `IN_FLIGHT` task as part of rollback; recovery remains manual and idempotent.

## 8. Activation boundary

No step in this document enables live execution. A future production activation requires a separate, explicit authorization process and must preserve the existing safety gates.

## 9. Release acceptance

A release is acceptable only when:

1. the complete test suite passes;
2. `compileall` succeeds;
3. the clean artifact builder succeeds;
4. the artifact contains no forbidden secrets/caches/bytecode;
5. sandbox/live configuration remains within the current safety contract; and
6. the release artifact is traceable to the tested source checkpoint.
## Writable runtime directories

The deployment container filesystem is read-only outside its writable temporary area. Set these variables in deployment: `SANOVA_DATA_DIR=/tmp/sanova`, `SANOVA_STATE_DIR=/tmp/sanova/tasks`, and `SANOVA_AUDIT_DIR=/tmp/sanova/audit`. Identity data remains in PostgreSQL via `DATABASE_URL`; these directories are only for sandbox execution state and audit files.

