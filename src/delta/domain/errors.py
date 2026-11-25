"""Domain errors raised by backup engines and surfaced to users."""

import errno
import re

from delta.domain.destination import DestinationState
from delta.i18n import _

DEVICE_ERRORS = frozenset({errno.EIO, errno.ENXIO, errno.ENODEV, errno.ESTALE})
PERMISSION_ERRORS = frozenset({errno.EACCES, errno.EPERM})


def engine_errno(text: str) -> int | None:
    """The number of the error of the system that an engine message carries («[Errno 30] Read-only file system»), if any."""
    found = re.search(r"\[Errno (\d+)\]", text)
    return int(found.group(1)) if found else None


def is_lock_message(text: str) -> bool:
    """Whether an engine message says the repository is locked, by another program or by an interrupted backup.

    A failure to make the lock that carries an error of the system («… the lock … ([Errno 30] Read-only file system)») is not
    that: the repository is not locked, the place cannot be written to.
    """
    lowered = text.lower()
    return "lock" in lowered and ("failed" in lowered or "timeout" in lowered) and engine_errno(text) is None


def is_full_message(text: str) -> bool:
    """Whether an engine message says that a disk has no room left (or a quota is used up)."""
    lowered = text.lower()
    return "no space left" in lowered or "quota exceeded" in lowered or "errno 28]" in lowered or "errno 122]" in lowered


def says_repository_is_full(text: str) -> bool:
    """Whether Borg says that the disk of the repository, and no other, is too full for it to go on.

    Unlike «no space left», which can be the home folder where Borg keeps its cache, this one is about the repository: Borg
    refuses to commit when what is free is less than what it needs («Insufficient free space to complete transaction»).
    """
    return "insufficient free space" in text.lower()


def state_from_error(text: str, location: str) -> DestinationState | None:
    """What a failure of the engine says about the place of the repository, when it says something; else None.

    Borg's own judgement that the repository has not enough room counts, and so does an error of the device (a disk that answers
    with I/O errors). A read-only or a permission error counts when it names the folder of the repository: Borg keeps a cache in
    the home folder, and a problem there is not the destination's: for a read-only place the folder has to be somewhere in what
    the engine said, for a permission error on the very line of the error. «No space left» is left to the probe, for the same reason.
    """
    if says_repository_is_full(text):
        return DestinationState.FULL
    number = engine_errno(text)
    if number in DEVICE_ERRORS:
        return DestinationState.IO_ERROR
    if number == errno.EROFS and location in text:
        return DestinationState.READ_ONLY
    if number in PERMISSION_ERRORS and any(location in line and f"[Errno {number}]" in line for line in text.splitlines()):
        return DestinationState.DENIED
    return None


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
        if self.state is DestinationState.IO_ERROR:
            return _("The place where your backups are kept reports errors: {location}")
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
        if self.state is DestinationState.IO_ERROR:
            return _("The drive reported an error while it was written to. Check its connection; if it keeps happening, the drive may be failing.")
        if self.state is DestinationState.FULL:
            return _("There is no room left there. Free some space, or choose another place in the preferences.")
        if self.state is DestinationState.READ_ONLY:
            return _("It is mounted so that nothing can be written to it. Mount it again for writing, or choose another place in the preferences. If this came after an error, the drive may be failing.")
        if self.state is DestinationState.DENIED:
            return _("You do not have permission to write there. Change its permissions, or choose another place in the preferences.")
        if self.state is DestinationState.EMPTY:
            return _("The folder is empty. Connect the drive that was there.")
        return _("The folder is not there. Connect the drive that holds your backups.")


class RepositoryLocked(DeltaError):
    pass


class PassphraseError(DeltaError):
    pass


class RepositoryDamaged(DeltaError):
    """The check of the repository found problems: what it said is kept, shortened."""

    def __init__(self, details: str) -> None:
        super().__init__(
            _(
                "The check found problems in your backups. Check the drive and, if the backups are still there, "
                "repair them with “borg check --repair”. Borg said: {details}"
            ).format(details=details[:300])
        )


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

    def __init__(self, message: str, returncode: int | None = None, report: str = "") -> None:
        """`report`: everything the engine said, when `message` is only a short account of it."""
        super().__init__(message)
        self.returncode = returncode
        self.report = report
