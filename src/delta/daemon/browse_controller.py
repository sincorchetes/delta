"""Opening a snapshot wins over backing up: stop the backup, mount, and give the repository back.

Borg cannot back up while a snapshot is mounted, nor mount while it backs up, and a backup cannot
be paused (docs/roadmap.md, M5). So opening interrupts the running backup (it resumes from its
checkpoint), a scheduled one is postponed, and closing starts the backup again.
"""

import logging
import time
import uuid
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from delta.application.browse_service import BrowseService
from delta.application.ports import MountUsage, SessionEvents
from delta.daemon.introspection import INTERFACE_NAME, OBJECT_PATH
from delta.daemon.job_calls import ERROR_UNAVAILABLE
from delta.daemon.job_runner import JobRunner
from delta.i18n import _

log = logging.getLogger(__name__)

REASON_REQUESTED = "requested"
REASON_OWNER_GONE = "owner-gone"
REASON_SESSION = "sleep-or-lock"
REASON_SHUTDOWN = "shutdown"
REASON_REPOSITORY_CHANGED = "repository-changed"
REASON_UNUSED = "unused"
CHECK_SECONDS = 30
UNUSED_GRACE_SECONDS = 120


class BrowseController:
    """Lives as long as the daemon; the BrowseService it is handed may change with the configuration."""

    def __init__(
        self,
        connection: Gio.DBusConnection,
        jobs: JobRunner,
        interrupt: Callable[[], None],
        resume: Callable[[bool], object],
        session_events: SessionEvents | None = None,
        on_postponed: Callable[[], None] | None = None,
        usage: MountUsage | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._on_postponed = on_postponed
        self._usage = usage
        self._clock = clock
        self._unused_since: float | None = None
        self._last_users: list[str] | None = None  # to log who uses the folder only when it changes
        self._timer = 0
        self._session = session_events
        self._connection = connection
        self._jobs = jobs
        self._interrupt = interrupt
        self._resume = resume
        self._open: BrowseService | None = None
        self._pending = False  # an opening was asked for and has not finished
        self._owed = False  # a scheduled backup was turned away meanwhile
        self._watch_id = 0
        if session_events is not None:
            session_events.watch(self._on_session_event)

    @property
    def is_open(self) -> bool:
        return self._open is not None

    def postpone(self) -> bool:
        """True (and remembered) if a backup must wait because a snapshot is open or being opened.

        The user is told once, not at every attempt (the schedule tries every hour).
        """
        if self._open is None and not self._pending:
            return False
        if not self._owed and self._on_postponed is not None:
            self._on_postponed()
        self._owed = True
        return True

    def mount(self, browse: BrowseService | None, parameters, sender: str, invocation) -> None:
        if browse is None:
            invocation.return_dbus_error(ERROR_UNAVAILABLE, _("browsing backups is not available"))
            return
        (snapshot,) = parameters.unpack()
        self._pending = True

        def task(on_progress):
            opened = False
            try:
                self._release()
                path = browse.open(snapshot)
                opened = True
            finally:
                self._pending = False
                if not opened:
                    self._give_back(resume=True)
            self._open = browse
            if self._session is not None:
                self._session.hold()  # sleeping waits until the folder is closed
            GLib.idle_add(self._watch, sender)
            return True, path

        if self._jobs.backup_running:
            self._interrupt()
        job_id = uuid.uuid4().hex
        self._jobs.submit_when_idle(job_id, task)
        invocation.return_value(GLib.Variant("(s)", (job_id,)))

    def unmount(self, invocation) -> None:
        invocation.return_value(GLib.Variant("(s)", (self.close(REASON_REQUESTED) or "",)))

    def close(self, reason: str, resume: bool = True) -> str | None:
        """Close what is open (if anything), tell the windows, and return the job that does it."""
        if self._open is None:
            return None
        log.info("closing the open snapshot: %s", reason)
        job_id = uuid.uuid4().hex

        def task(on_progress):
            try:
                self._release()
            finally:
                self._give_back(resume)
            return True, ""

        self._jobs.submit_when_idle(job_id, task)
        self._connection.emit_signal(
            None, OBJECT_PATH, INTERFACE_NAME, "SnapshotClosed", GLib.Variant("(s)", (reason,))
        )
        return job_id

    def _release(self) -> None:
        opened, self._open = self._open, None
        GLib.idle_add(self._unwatch)
        try:
            if opened is not None:
                opened.close()
        finally:
            if self._session is not None:
                self._session.release()  # only now may the computer go to sleep

    def _give_back(self, resume: bool) -> None:
        """The repository is free: start the backup that was interrupted or turned away."""
        owed, self._owed = self._owed, False

        def start() -> None:
            self._resume(owed)

        if resume:
            self._jobs.when_idle(start)

    def _watch(self, sender: str) -> bool:
        self._unwatch()
        self._watch_id = Gio.bus_watch_name_on_connection(
            self._connection, sender, Gio.BusNameWatcherFlags.NONE, None, self._on_vanished
        )
        if self._usage is not None:
            self._unused_since = self._last_users = None
            self._timer = GLib.timeout_add_seconds(CHECK_SECONDS, self._check_usage)
        return GLib.SOURCE_REMOVE

    def _unwatch(self) -> bool:
        if self._watch_id:
            Gio.bus_unwatch_name(self._watch_id)
            self._watch_id = 0
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        return GLib.SOURCE_REMOVE

    def _check_usage(self) -> bool:
        """A forgotten folder would hold back every backup: once nothing has used it for a while
        (no open file, no window showing it), close it. A long copy keeps its file open, so it is
        never cut short."""
        if self._open is None or self._usage is None:
            return GLib.SOURCE_REMOVE
        now = self._clock()
        users = self._usage.users(self._open.mountpoint)
        if users != self._last_users:
            self._last_users = users
            log.info("the open snapshot is used by: %s", "; ".join(users) or "nobody")
        if users:
            self._unused_since = None
        elif self._unused_since is None:
            self._unused_since = now
        elif now - self._unused_since >= UNUSED_GRACE_SECONDS:
            self._timer = 0
            self.close(REASON_UNUSED)
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _on_session_event(self) -> None:
        self.close(REASON_SESSION)

    def _on_vanished(self, _connection, name) -> None:
        log.info("%s went away with a snapshot open; closing it", name)
        self.close(REASON_OWNER_GONE)
