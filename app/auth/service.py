from __future__ import annotations
from app.identity.authorization import Permission

class AuthenticationRequired(PermissionError):
    pass

class ConsentRequired(PermissionError):
    pass

class AuthenticatedApplicationService:
    """Identity-aware boundary. The underlying application remains unchanged."""
    CONSENT_SCOPE = "physical-action"
    CONSENT_VERSION = "v1"

    def __init__(self, identity, application):
        self.identity = identity
        self.application = application

    def register(self, email, password):
        return self.identity.register(email, password)

    def login(self, email, password):
        return self.identity.authenticate(email, password)

    def logout(self, token):
        self.identity.logout(token)

    def current_user(self, token):
        return self.identity.current_user(token)

    def grant_execution_consent(self, token):
        user = self._authenticated(token)
        self.identity.authorization.grant_consent(user, self.CONSENT_SCOPE, self.CONSENT_VERSION)

    def revoke_execution_consent(self, token):
        user = self._authenticated(token)
        self.identity.authorization.revoke_consent(user, self.CONSENT_SCOPE)

    def execute_intent(self, token, text):
        self._authorize_execution(token)
        return self.application.execute_intent(text)

    def execute_spec(self, token, spec):
        self._authorize_execution(token)
        return self.application.execute_spec(spec)

    def _authenticated(self, token):
        user = self.identity.current_user(token)
        if user is None:
            raise AuthenticationRequired("authentication required")
        return user

    def _authorize_execution(self, token):
        user = self._authenticated(token)
        if not self.identity.authorization.has_permission(user, Permission.EXECUTE):
            raise AuthenticationRequired("execution permission required")
        if not self.identity.authorization.has_consent(user, self.CONSENT_SCOPE, self.CONSENT_VERSION):
            raise ConsentRequired("consent required for physical-action v1")
        return user
