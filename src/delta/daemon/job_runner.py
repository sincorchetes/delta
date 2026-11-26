"""Runs one job at a time off the main loop and publishes it as D-Bus signals."""

import logging
import threading
import time
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import GLib

from delta.daemon.introspection import INTERFACE_NAME, OBJECT_PATH
from delta.domain.destination import DestinationState
from delta.domain.errors import DeltaError, DestinationUnavailable
from delta.domain.progress import ProgressEvent

log = logging.getLogger(__name__)

INDETERMINATE = -1.0

ProgressSink = Callable[[ProgressEvent], None]
Task = Callable[[ProgressSink], tuple[bool, str]]


def _nothing_known() -> DestinationState:
    return DestinationState.AVAILABLE


class JobAlreadyRunning(Exception):
    pass


class JobRunner:
    def __init__(self, connection, place: Callable[[], DestinationState] = _nothing_known) -> None:
        """`place` tells, without waiting, whether the place of the backups can be used: a drive pulled out is known before a
        backup tries it."""
        self._connection = connection
        self._place = place
        self._lock = threading.Lock()
        self._running = False
        self._backup_running = False
        self._checking = False
        self._idle_callbacks: list[Callable[[], None]] = []
        self.last_backup = 0
        self.last_error = ""  # why the latest backup failed; empty after a good one
        self.unavailable = ""  # where the repository should be, while the latest backup could not use it; else empty
        self.unavailable_reason = ""  # why, as the value of a DestinationState: missing, empty, full, read-only or denied

    def clear_error(self) -> None:
        """The reason of the last failure no longer applies (e.g. the repository was unlocked)."""
        self.last_error = ""

    def seed_last_backup(self, timestamp: int) -> None:
        """A backup made before this process started (known from the repository itself)."""
        self.last_backup = max(self.last_backup, timestamp)

    @property
    def status(self) -> str:
        if self._running:
            return "checking" if self._checking else "running"
        return "unavailable" if self.unavailable or self._place() is not DestinationState.AVAILABLE else "idle"

    @property
    def checking(self) -> bool:
        """A check of the repository runs now."""
        return self._checking

    @property
    def reason(self) -> str:
        """Why the place cannot be used, as the value of a DestinationState, while it cannot; else empty."""
        if self.unavailable_reason:
            return self.unavailable_reason
        place = self._place()
        return "" if place is DestinationState.AVAILABLE else place.value

    def when_idle(self, callback: Callable[[], None]) -> None:
        """Run `callback` now if no job runs, else right after the job ends.

        Used to apply configuration changes without interrupting a backup.
        Repeated registrations of the same callback coalesce into one.
        """
        with self._lock:
            if self._running:
                if callback not in self._idle_callbacks:
                    self._idle_callbacks.append(callback)
                return
        callback()

    @property
    def backup_running(self) -> bool:
        return self._backup_running

    def submit_when_idle(self, job_id: str, task: Task) -> None:
        """Start `task` as soon as no job is running; it never interrupts one by itself."""

        def start() -> None:
            try:
                self.submit(job_id, task)
            except JobAlreadyRunning:  # another job slipped in between
                self.when_idle(start)

        self.when_idle(start)

    def submit(self, job_id: str, task: Task, records_backup: bool = False, checking: bool = False) -> None:
        with self._lock:
            if self._running:
                raise JobAlreadyRunning()
            self._running = True
            self._backup_running = records_backup
            self._checking = checking
        threading.Thread(target=self._work, args=(job_id, task, records_backup), daemon=True).start()

    def _work(self, job_id: str, task: Task, records_backup: bool) -> None:
        def on_progress(event: ProgressEvent) -> None:
            self._emit("Progress", GLib.Variant("(sds)", (job_id, INDETERMINATE, event.path)))

        ok, message, unreachable = False, "unexpected error", None
        try:
            ok, message = task(on_progress)
        except DestinationUnavailable as err:
            message, unreachable = str(err), err
        except DeltaError as err:
            message = str(err)
        except Exception:
            log.exception("job %s crashed", job_id)
            raise
        finally:
            self._record_outcome(job_id, ok, message, records_backup, unreachable)
            with self._lock:
                self._running = self._backup_running = self._checking = False
                pending, self._idle_callbacks = self._idle_callbacks, []
            self._emit("BackupFinished", GLib.Variant("(sbs)", (job_id, ok, message)))
            for callback in pending:
                GLib.idle_add(self._run_when_idle, callback)

    def _record_outcome(
        self, job_id: str, ok: bool, message: str, records_backup: bool, unreachable: DestinationUnavailable | None = None
    ) -> None:
        if unreachable is not None:
            log.info("job %s waits, the place of the backups cannot be used: %s", job_id, message)
        elif not ok:
            log.warning("job %s did not succeed: %s", job_id, message)
        elif message:  # done, but with something to say (Borg's warnings, a failed prune): the notification cuts it short
            log.warning("job %s finished with warnings:\n%s", job_id, message)
        if not records_backup:
            return
        if ok:
            self.last_backup = int(time.time())
        # A place that cannot be reached is a state of its own, not the last error: it ends by itself when it is back.
        self.unavailable = "" if unreachable is None else unreachable.location
        self.unavailable_reason = "" if unreachable is None else unreachable.state.value
        self.last_error = "" if ok or unreachable is not None else message

    def _run_when_idle(self, callback: Callable[[], None]) -> bool:
        """Main-loop hop; re-defers if another job started in between."""
        self.when_idle(callback)
        return False

    def _emit(self, signal: str, parameters) -> None:
        GLib.idle_add(
            lambda: self._connection.emit_signal(None, OBJECT_PATH, INTERFACE_NAME, signal, parameters)
            and False
        )
