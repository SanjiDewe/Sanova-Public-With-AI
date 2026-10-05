# Sanova — Google Integration Changes add gmail api , calendar api , sheet api

ADD/
- app/integrations/accounts/__init__.py
- app/integrations/accounts/crypto.py
- app/integrations/accounts/store.py
- app/integrations/google/__init__.py
- app/integrations/google/client.py
- app/integrations/google/service.py
- tests/test_google_integration.py


- `.env.example`
- `app/ai/agent.py`
- `app/ai/tools.py`
- `app/config.py`
- `app/identity/store.py`
- `app/web/app.py`
- `app/web/templates/private/integrations.html`
- `pyproject.toml`
- `tests/test_pluggable_integrations.py`

`pip install -e .`

`pip install 'cryptography>=43,<47'`

`.env`

`SANOVA_GOOGLE_CLIENT_ID=...`
`SANOVA_GOOGLE_CLIENT_SECRET=...`
`SANOVA_GOOGLE_REDIRECT_URI=...`

`SANOVA_GOOGLE_TOKEN_ENCRYPTION_KEY=...`

`SANOVA_GOOGLE_REDIRECT_URI`

Scope Gmail / Calendar / Sheets digunakan ketika user melakukan **Connect Google**

`pytest -q tests/test_google_integration.py tests/test_pluggable_integrations.py`

`pytest -q`

Google connection have :

- OAuth connection
- encrypted access token storage
- encrypted refresh token storage
- token refresh
- disconnect/revoke
- Gmail read/send client methods
- Calendar list/create client methods
- Sheets read/update client methods
- AI read tools untuk Gmail, Calendar, Sheets
