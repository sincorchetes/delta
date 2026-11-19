"""A backup run and its state machine."""

from dataclasses import dataclass, field
from enum import Enum

from delta.domain.errors import DestinationUnavailable
from delta.i18n import _


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    WARNINGS = "warnings"
    INTERRUPTED = "interrupted"
    UNAVAILABLE = "unavailable"  # the place where the copy goes cannot be reached: not a failure, it waits
    FAILED = "failed"


_TRANSITIONS = {
    JobState.PENDING: {JobState.RUNNING, JobState.FAILED, JobState.UNAVAILABLE},
    JobState.RUNNING: {
        JobState.SUCCEEDED,
        JobState.WARNINGS,
        JobState.INTERRUPTED,
        JobState.UNAVAILABLE,
        JobState.FAILED,
    },
    JobState.SUCCEEDED: set(),
    JobState.WARNINGS: set(),
    JobState.INTERRUPTED: set(),
    JobState.UNAVAILABLE: set(),
    JobState.FAILED: set(),
}


@dataclass
class BackupJob:
    id: str
    sources: tuple[str, ...]
    excludes: tuple[str, ...] = ()
    state: JobState = JobState.PENDING
    message: str = field(default="")
    unavailable: DestinationUnavailable | None = None  # why, when the state is UNAVAILABLE

    def __post_init__(self) -> None:
        if not self.sources:
            raise ValueError(_("a backup job needs at least one source"))

    def start(self) -> None:
        self._move(JobState.RUNNING)

    def succeed(self) -> None:
        self._move(JobState.SUCCEEDED)

    def warn(self, message: str) -> None:
        """The snapshot exists but the engine reported problems (e.g. unreadable files)."""
        self._move(JobState.WARNINGS)
        self.message = message

    def interrupt(self) -> None:
        """Stopped on purpose; no snapshot was completed and the job must be resumed."""
        self._move(JobState.INTERRUPTED)

    def wait_for_destination(self, error: DestinationUnavailable) -> None:
        """The place where the copy goes cannot be reached: nothing was made, and it is tried again later."""
        self._move(JobState.UNAVAILABLE)
        self.unavailable = error
        self.message = str(error)

    def fail(self, message: str) -> None:
        self._move(JobState.FAILED)
        self.message = message

    def _move(self, target: JobState) -> None:
        if target not in _TRANSITIONS[self.state]:
            raise ValueError(f"cannot go from {self.state.value} to {target.value}")
        self.state = target
