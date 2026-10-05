# Sanova

> A sandbox-first execution platform for orchestrating digital workflows and pluggable integrations.

Sanova is a Python application built around explicit runtime boundaries, pluggable providers, safety controls, and testable execution workflows. The current public release is intentionally **sandbox-only**: live physical execution is disabled by design.

## What is in this repository?

- **Execution engine** — task contracts, planning, orchestration, execution, and state management.
- **AI layer** — AI management, agent/tool interfaces, and provider abstraction.
- **Integrations** — pluggable email, OAuth, Google, webhook, and provider adapters.
- **Identity & authentication** — account storage and authentication boundaries.
- **Safety & readiness** — activation gates, auditability, deployment checks, and production-readiness controls.
- **Web application** — FastAPI application, templates, static assets, localization, and account/integration flows.

## Current safety boundary

Sanova is currently configured for sandbox operation. The public repository does **not** enable live physical execution.

The expected safe defaults are:

```text
SANOVA_ENVIRONMENT=sandbox
SANOVA_LIVE_EXECUTION=false
SANOVA_SANDBOX_HTTP_ENABLED=false
```

Runtime configuration is resolved through `RuntimeConfig` / `load_runtime_config()`. Production activation and live physical execution remain hard-locked by the application safety boundary.

## Tech stack

- Python 3.11+
- FastAPI
- Uvicorn
- Jinja2
- PostgreSQL via Psycopg
- Cryptography / Fernet-based secret protection
- Pytest

## Quick start

### 1. Create a virtual environment

```bash
python -m venv .venv
```

Activate it using the command appropriate for your shell, then install the project:

```bash
python -m pip install --upgrade pip
pip install -e .
```

For development and tests:

```bash
pip install -e '.[test]'
```

### 2. Configure the environment

Copy `.env.example` to `.env` and set only the values required for the integration you are testing. Never commit `.env` or real credentials.

The default sandbox configuration is designed to avoid live external execution.

### 3. Run the web application

```bash
uvicorn app.web.main:app --reload
```

The application will be available at `http://127.0.0.1:8000` by default.

### 4. Run the test suite

```bash
pytest -q
```

Compile checks can also be run with:

```bash
python -m compileall app tests
```

## Repository structure

```text
app/
├── activation/       Activation boundaries
├── ai/               AI management, agents, tools, credentials
├── application/      Application services
├── audit/            Audit support
├── auth/             Authentication boundaries
├── contracts/        Domain contracts
├── core/             Core orchestration, planning, safety, persistence
├── deployment/       Deployment readiness
├── identity/         Identity and account storage
├── integrations/     Pluggable external integrations
├── intent/           Intent handling
├── locales/          Localization resources
├── management/       Management APIs and services
├── models/           Application models
├── orchestration/    Workflow orchestration
├── persistence/      Persistence services
├── planner/          Planning services
├── providers/        Provider abstractions/adapters
├── readiness/        Readiness checks
├── safety/           Safety controls
└── web/              FastAPI app, templates, and static assets

tests/                Automated test suite
scripts/              Release/artifact utilities
docs/                 Public technical documentation
```

## Provider lifecycle

Provider factories are lazy: providers are registered without eager construction and instantiated only when selected. Registration does not perform external setup or instantiate every provider eagerly.

## Configuration and secrets

`.env.example` is the public configuration reference. Credentials belong in the runtime environment, never in source control.

For Google integrations, see [`docs/google-integrations.md`](docs/google-integrations.md).

If a credential has ever been exposed through an artifact or repository history, rotate/revoke it with the relevant provider before using it again.

## Release artifact hygiene

Sanova includes a release-artifact builder:

```bash
python scripts/build_artifact.py --output dist/sanova-source.zip
```

Release artifacts must not contain:

- `.env` files or credentials
- `.git`
- Python bytecode
- test/runtime caches
- local SQLite state
- other machine-specific runtime data

## Deployment

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the deployment-readiness contract, persistence expectations, rollback guidance, and activation boundary.

The deployment documentation describes operational requirements; it does not authorize production or live physical execution.

## Contributing

Contributions should preserve the project's safety boundaries and keep external integrations dependency-injected and testable. Before opening a pull request, run:

```bash
pytest -q
python -m compileall app tests
```

Keep credentials, local state, generated artifacts, and machine-specific files out of commits.

## Security

Please do not report security-sensitive issues in public issues. See [`SECURITY.md`](SECURITY.md) for the preferred reporting process and repository security expectations.

## License

No license is currently declared for this repository. Until a license is added, public visibility should not be interpreted as a grant of permission to reuse, modify, or redistribute the source.
