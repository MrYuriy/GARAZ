from app.enums.base import BaseStrEnum


class AuditAction(BaseStrEnum):
    """What happened. Stored as text, so new actions need no migration."""

    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT_ALL = "auth.logout_all"
    AUTH_PASSWORD_CHANGED = "auth.password_changed"
    # A refresh token came back after it had been retired: one copy leaked.
    AUTH_TOKEN_REUSE = "auth.token_reuse"

    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"

    # resource_type is the DictionaryKind, e.g. "truck-types".
    DICTIONARY_CREATED = "dictionary.created"
    DICTIONARY_UPDATED = "dictionary.updated"
