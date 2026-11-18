"""Pairs one started job with its BackupFinished signal, whichever of the two arrives first."""

from collections.abc import Callable

Done = Callable[[bool, str], None]


class JobTracker:
    def __init__(self) -> None:
        self._done: Done | None = None
        self._job: str | None = None
        self._early: dict[str, tuple[bool, str]] = {}  # a result can beat the call's reply

    @property
    def busy(self) -> bool:
        return self._done is not None

    def begin(self, done: Done) -> None:
        """Call just before starting the job; `done(ok, message)` runs exactly once."""
        self._done, self._job = done, None

    def on_started(self, job_id: str | None, error: str | None) -> None:
        done = self._done
        if done is None:
            return
        if error or job_id is None:
            self._complete(done, False, error or "")
            return
        self._job = job_id
        if job_id in self._early:
            self._complete(done, *self._early.pop(job_id))

    def on_finished(self, job_id: str, ok: bool, message: str) -> None:
        done = self._done
        if done is None:
            return
        if self._job is None:
            self._early[job_id] = (ok, message)
        elif job_id == self._job:
            self._complete(done, ok, message)

    def _complete(self, done: Done, ok: bool, message: str) -> None:
        self._done = self._job = None
        self._early.clear()
        done(ok, message)
