# Contributing to Sanova

Thanks for contributing.

## Development setup

```bash
python -m venv .venv
pip install -e '.[test]'
```

Use `.env.example` as the starting point for local configuration. Keep real credentials out of source control.

## Before opening a pull request

Run the full test suite:

```bash
pytest -q
python -m compileall app tests
```

If your change affects an integration, safety boundary, configuration path, or release artifact, add or update the relevant tests.

## Project principles

- Keep sandbox and live execution boundaries explicit.
- Prefer dependency injection and lazy provider construction.
- Keep external integrations testable without requiring live credentials.
- Avoid changing unrelated application behavior in a focused pull request.
- Do not commit generated caches, local databases, secrets, or environment-specific files.

## Pull requests

A useful pull request should explain:

1. what changed;
2. why it changed;
3. how it was tested; and
4. any safety, configuration, migration, or deployment implications.

Small, focused pull requests are easier to review and safer to validate.
