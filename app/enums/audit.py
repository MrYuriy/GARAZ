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

    TRUCK_CREATED = "truck.created"
    TRUCK_UPDATED = "truck.updated"
    # The old sticker stopped working; a new one has to be printed.
    TRUCK_QR_REISSUED = "truck.qr_reissued"
    TRUCK_DELETED = "truck.deleted"

    TRUCK_MANUFACTURER_CREATED = "truck_manufacturer.created"
    TRUCK_MANUFACTURER_UPDATED = "truck_manufacturer.updated"
    # Its models go with it; refused while a truck uses it.
    TRUCK_MANUFACTURER_DELETED = "truck_manufacturer.deleted"
    TRUCK_MODEL_CREATED = "truck_model.created"
    TRUCK_MODEL_UPDATED = "truck_model.updated"
    TRUCK_MODEL_DELETED = "truck_model.deleted"

    OPERATOR_CREATED = "operator.created"
    OPERATOR_UPDATED = "operator.updated"
    # The old operator card stopped working; a new one has to be printed.
    OPERATOR_QR_REISSUED = "operator.qr_reissued"

    PERMIT_CREATED = "permit.created"
    PERMIT_UPDATED = "permit.updated"
    # Set by the daily pass, so user_id is null.
    PERMIT_EXPIRED = "permit.expired"
    PERMIT_DOCUMENT_ATTACHED = "permit.document_attached"
    PERMIT_DOCUMENT_REMOVED = "permit.document_removed"
