"""Domain errors raised by backup engines and surfaced to users."""

from delta.domain.destination import DestinationState
from delta.i18n import _


def is_lock_message(text: str) -> bool:
    """Whether an engine message says the repository could not be locked."""
    lowered = text.lower()
    return "lock" in lowered and ("failed" in lowered or "timeout" in lowered)


def is_full_message(text: str) -> bool:
    """Whether an engine message says that a disk has no room left (or a quota is used up)."""
    lowered = text.lower()
    return "no space left" in lowered or "quota exceeded" in lowered or "errno 28]" in lowered or "errno 122]" in lowered


class DeltaError(Exception):
    """Base class for every Delta domain error."""


class InvalidPath(DeltaError):
    pass


class SnapshotNotFound(DeltaError):
    pass


class RepositoryNotFound(DeltaError):
    """The folder is there, but it holds no repository (another folder, or another disk, is at that place)."""


class DestinationUnavailable(DeltaError):
    """The place where the backups are kept cannot be used right now, and why (`state`).

    Not a failure of the backup: a drive that is not connected comes back, a full one gets room, a read-only one is mounted
    again, and the backup waits for it. Each cause has its own message and its own hint. It is told apart from
    `RepositoryNotFound` (a folder that is there and holds no repository).
    """

    def __init__(self, location: str, state: DestinationState) -> None:
        self.location, self.state = location, state
        super().__init__(self._message().format(location=location))

    def _message(self) -> str:
        if self.state is DestinationState.OTHER_DRIVE:
            return _("A drive is connected where your backups were kept, but they are not on it: {location}")
        if self.state is DestinationState.OTHER_REPOSITORY:
            return _("The repository at {location} is not the one your backups were made in")
        if self.state is DestinationState.FULL:
            return _("The place where your backups are kept is full: {location}")
        if self.state is DestinationState.READ_ONLY:
            return _("The place where your backups are kept is read-only: {location}")
        if self.state is DestinationState.DENIED:
            return _("You cannot write in the place where your backups are kept: {location}")
        return _("The place where your backups are kept is not available: {location}")

    @property
    def hint(self) -> str:
        """What to do about it, in a sentence."""
        if self.state is DestinationState.OTHER_REPOSITORY:
            return _("Connect the drive that holds your backups. If this repository is the right one, choose it again in the preferences, with its passphrase.")
        if self.state is DestinationState.OTHER_DRIVE:
            return _("This is not the drive that holds your backups. Connect that one, or choose another place in the preferences.")
        if self.state is DestinationState.FULL:
            return _("There is no room left there. Free some space, or choose another place in the preferences.")
        if self.state is DestinationState.READ_ONLY:
            return _("It is mounted so that nothing can be written to it. Mount it again for writing, or choose another place in the preferences.")
        if self.state is DestinationState.DENIED:
            return _("You do not have permission to write there. Change its permissions, or choose another place in the preferences.")
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
