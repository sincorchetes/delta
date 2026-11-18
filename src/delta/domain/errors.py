"""Domain errors raised by backup engines and surfaced to users."""


def is_lock_message(text: str) -> bool:
    """Whether an engine message says the repository could not be locked."""
    lowered = text.lower()
    return "lock" in lowered and ("failed" in lowered or "timeout" in lowered)


class DeltaError(Exception):
    """Base class for every Delta domain error."""


class InvalidPath(DeltaError):
    pass


class SnapshotNotFound(DeltaError):
    pass


class RepositoryNotFound(DeltaError):
    pass


class RepositoryLocked(DeltaError):
    pass


class PassphraseError(DeltaError):
    pass


class BackupWarning(DeltaError):
    """The backup was created, but the engine reported non-fatal problems."""


class BackupInterrupted(DeltaError):
    """The engine was stopped on purpose (e.g. system shutdown); the backup must be resumed."""


class SecretStoreError(DeltaError):
    """The secret service (keyring) is unreachable, locked or refused the request."""


class SchedulerError(DeltaError):
    """The scheduler backend (systemd, portal) could not apply the schedule."""


class EngineError(DeltaError):
    """The backup engine failed for a reason without a dedicated type."""

    def __init__(self, message: str, returncode: int | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode
