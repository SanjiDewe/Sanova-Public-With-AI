# Architecture Overview

Sanova is organized around explicit boundaries between the web application, application services, execution/orchestration, integrations, persistence, and safety/readiness controls.

## High-level flow

```text
HTTP request
    │
    ▼
FastAPI / Web layer
    │
    ▼
Application + management services
    │
    ├──────────────► Identity / persistence
    │
    ├──────────────► Planner / intent
    │
    ├──────────────► Orchestration / execution
    │                         │
    │                         ▼
    │                  Provider abstractions
    │                         │
    │                         ▼
    │                  External integrations
    │
    └──────────────► AI layer / tools

Safety, activation, audit, and readiness boundaries apply across the execution path.
```

## Runtime configuration

Runtime decisions should use `RuntimeConfig` or `load_runtime_config()` rather than relying on import-time environment constants.

The public release defaults to sandbox execution:

```text
SANOVA_ENVIRONMENT=sandbox
SANOVA_LIVE_EXECUTION=false
SANOVA_SANDBOX_HTTP_ENABLED=false
```

## Provider lifecycle

Providers are registered through factories and constructed lazily when selected. Registration should not perform external setup or instantiate every provider eagerly.

## Persistence

Identity data can use PostgreSQL through `DATABASE_URL`. Sandbox execution state and audit output use configurable runtime directories; container deployments should use writable ephemeral paths as described in `DEPLOYMENT.md`.
