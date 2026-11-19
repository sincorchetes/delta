"""Domain errors raised by backup engines and surfaced to users."""

from delta.domain.destination import DestinationState
from delta.i18n import _


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
    """The folder is there, but it holds no repository (another folder, or another disk, is at that place)."""


class DestinationUnavailable(DeltaError):
    """The place where the backups are kept cannot be reached right now.

    Not a failure of the backup: a drive that is not connected, or a folder that is gone, comes back, and the backup waits
    for it. It is told apart from `RepositoryNotFound` (a folder that is there and holds no repository).
    """

    def __init__(self, location: str, state: DestinationState) -> None:
        self.location, self.state = location, state
        super().__init__(_("The place where your backups are kept is not available: {location}").format(location=location))

    @property
    def hint(self) -> str:
        """What to do about it, in a sentence."""
        if self.state is DestinationState.EMPTY:
            return _("The folder is empty. Connect the drive that was there.")
        return _("The folder is not there. Connect the drive that holds your backups.")


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
