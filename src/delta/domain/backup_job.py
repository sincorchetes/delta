"""A backup run and its state machine."""

from dataclasses import dataclass, field
from enum import Enum

from delta.i18n import _


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    WARNINGS = "warnings"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


_TRANSITIONS = {
    JobState.PENDING: {JobState.RUNNING, JobState.FAILED},
    JobState.RUNNING: {
        JobState.SUCCEEDED,
        JobState.WARNINGS,
        JobState.INTERRUPTED,
        JobState.FAILED,
    },
    JobState.SUCCEEDED: set(),
    JobState.WARNINGS: set(),
    JobState.INTERRUPTED: set(),
    JobState.FAILED: set(),
}


@dataclass
class BackupJob:
    id: str
    sources: tuple[str, ...]
    excludes: tuple[str, ...] = ()
    state: JobState = JobState.PENDING
    message: str = field(default="")

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

    def fail(self, message: str) -> None:
        self._move(JobState.FAILED)
        self.message = message

    def _move(self, target: JobState) -> None:
        if target not in _TRANSITIONS[self.state]:
            raise ValueError(f"cannot go from {self.state.value} to {target.value}")
        self.state = target
