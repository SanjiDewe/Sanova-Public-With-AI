# Security Policy

## Scope

Sanova is currently a sandbox-first project. Live physical execution is intentionally disabled by the application's safety boundary.

## Reporting a vulnerability

Please do **not** disclose exploitable vulnerabilities, credentials, tokens, private data, or detailed attack instructions in a public issue.

If this repository is configured with a private security-reporting channel, use that channel. Otherwise, contact the project maintainer privately before public disclosure.

When reporting a security issue, include:

- a concise description of the vulnerability;
- affected component(s) and version/commit, if known;
- safe reproduction steps or a minimal proof of concept;
- the potential impact; and
- any suggested mitigation.

Please avoid including real credentials or personal data in reports.

## Secret handling

- Never commit `.env` files or real provider credentials.
- Use `.env.example` as the public configuration reference.
- Rotate/revoke any credential that may have been exposed.
- Do not use production credentials for sandbox testing.
- Treat repository history and generated artifacts as sensitive if they may contain secrets.

## Safety boundary

Changes must not bypass or weaken the existing sandbox/live-execution gates as part of ordinary development or integration work.
