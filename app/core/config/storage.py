# Where uploaded files live (scanned permit documents now, incident photos later).
from app.core.config.base import BaseConfig


class StorageConfig(BaseConfig):
    # A directory on a Docker volume. Files are addressed by key only, so moving
    # to S3-compatible storage later changes the backend, not the callers.
    STORAGE_DIR: str = "storage"
    # One scanned document: a multi-page PDF or a phone photo.
    MAX_DOCUMENT_MB: int = 15


class PermitConfig(BaseConfig):
    # Run the daily "Wygasłe" pass inside the API process. Off where several
    # processes share one database and another one already runs it (harmless
    # either way: the pass is idempotent).
    PERMIT_EXPIRY_ENABLED: bool = True
    # Local time (TIMEZONE) of the daily pass. Also runs once at start-up.
    PERMIT_EXPIRY_HOUR: int = 0
    PERMIT_EXPIRY_MINUTE: int = 5
