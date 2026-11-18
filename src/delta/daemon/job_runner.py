"""Runs one job at a time off the main loop and publishes it as D-Bus signals."""

import logging
import threading
import time
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import GLib

from delta.daemon.introspection import INTERFACE_NAME, OBJECT_PATH
from delta.domain.errors import DeltaError
from delta.domain.progress import ProgressEvent

log = logging.getLogger(__name__)

INDETERMINATE = -1.0

ProgressSink = Callable[[ProgressEvent], None]
Task = Callable[[ProgressSink], tuple[bool, str]]


class JobAlreadyRunning(Exception):
    pass


class JobRunner:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._lock = threading.Lock()
        self._running = False
        self._backup_running = False
        self._idle_callbacks: list[Callable[[], None]] = []
        self.last_backup = 0
        self.last_error = ""  # why the latest backup failed; empty after a good one

    def clear_error(self) -> None:
        """The reason of the last failure no longer applies (e.g. the repository was unlocked)."""
        self.last_error = ""

    def seed_last_backup(self, timestamp: int) -> None:
        """A backup made before this process started (known from the repository itself)."""
        self.last_backup = max(self.last_backup, timestamp)

    @property
    def status(self) -> str:
        return "running" if self._running else "idle"

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

    def submit(self, job_id: str, task: Task, records_backup: bool = False) -> None:
        with self._lock:
            if self._running:
                raise JobAlreadyRunning()
            self._running = True
            self._backup_running = records_backup
        threading.Thread(target=self._work, args=(job_id, task, records_backup), daemon=True).start()

    def _work(self, job_id: str, task: Task, records_backup: bool) -> None:
        def on_progress(event: ProgressEvent) -> None:
            self._emit("Progress", GLib.Variant("(sds)", (job_id, INDETERMINATE, event.path)))

        ok, message = False, "unexpected error"
        try:
            ok, message = task(on_progress)
        except DeltaError as err:
            message = str(err)
        except Exception:
            log.exception("job %s crashed", job_id)
            raise
        finally:
            self._record_outcome(job_id, ok, message, records_backup)
            with self._lock:
                self._running = self._backup_running = False
                pending, self._idle_callbacks = self._idle_callbacks, []
            self._emit("BackupFinished", GLib.Variant("(sbs)", (job_id, ok, message)))
            for callback in pending:
                GLib.idle_add(self._run_when_idle, callback)

    def _record_outcome(self, job_id: str, ok: bool, message: str, records_backup: bool) -> None:
        if not ok:
            log.warning("job %s did not succeed: %s", job_id, message)
        if not records_backup:
            return
        if ok:
            self.last_backup = int(time.time())
        self.last_error = "" if ok else message

    def _run_when_idle(self, callback: Callable[[], None]) -> bool:
        """Main-loop hop; re-defers if another job started in between."""
        self.when_idle(callback)
        return False

    def _emit(self, signal: str, parameters) -> None:
        GLib.idle_add(
            lambda: self._connection.emit_signal(None, OBJECT_PATH, INTERFACE_NAME, signal, parameters)
            and False
        )
