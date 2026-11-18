"""SnapshotMounter on `borg mount` (FUSE): only the native install can offer it."""

import os
import signal
import threading
import time
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from delta.domain.errors import DeltaError, EngineError
from delta.domain.repository import Repository
from delta.i18n import _
from delta.infrastructure import borg_commands as commands
from delta.infrastructure.borg_parsing import error_for
from delta.infrastructure.borg_runner import BorgRunner

READY_TIMEOUT = 30.0  # seconds borg gets to show the folder
STOP_TIMEOUT = 10.0  # seconds it gets to leave after SIGTERM
POLL = 0.1


class BorgMounter:
    """Keeps one `borg mount` process alive; it holds the repository for as long as it runs.

    Stopping that process is not enough to remove the folder (verified with
    scripts/verify_mount_vs_backup.sh): a lazy unmount always follows.
    """

    def __init__(
        self,
        runner: BorgRunner,
        binary: str = "borg",
        ready_timeout: float = READY_TIMEOUT,
        stop_timeout: float = STOP_TIMEOUT,
        is_mounted: Callable[[str], bool] = os.path.ismount,
    ) -> None:
        self._runner = runner
        self._binary = binary
        self._ready_timeout = ready_timeout
        self._stop_timeout = stop_timeout
        self._is_mounted = is_mounted
        self._lock = threading.Lock()
        self._process = None
        self._ended = threading.Event()
        self._stderr: list[str] = []

    def mount(self, repo: Repository, snapshot: str, mountpoint: str) -> None:
        with self._lock:
            if self._process is not None:
                raise EngineError(_("a snapshot is already open"))
            argv = [self._binary, *commands.mount(repo, snapshot, mountpoint)[1:]]
            launcher = self._runner.launcher(repo, flags=Gio.SubprocessFlags.STDERR_PIPE)
            try:
                process = launcher.spawnv(argv)
            except GLib.Error as err:
                raise EngineError(_("cannot run {program}: {reason}").format(program=self._binary, reason=err.message)) from err
            self._process, self._ended, self._stderr = process, threading.Event(), []
            threading.Thread(target=self._wait, args=(process, self._ended, self._stderr), daemon=True).start()
            ended, stderr = self._ended, self._stderr
        failure = self._wait_until_shown(mountpoint, ended)
        if failure is not None:
            try:
                self.unmount(mountpoint)
            except EngineError:
                pass  # the reason the folder never opened matters more
            raise self._failure(process, stderr, failure)

    @staticmethod
    def _wait(process, ended: threading.Event, stderr: list[str]) -> None:
        try:
            stderr.append(process.communicate_utf8(None, None)[2] or "")
        finally:
            ended.set()  # whatever happened, nobody should keep waiting for a process that is gone

    def _wait_until_shown(self, mountpoint: str, ended: threading.Event) -> str | None:
        """None once the folder is there; else why it never was ('exited' or 'timeout')."""
        deadline = time.monotonic() + self._ready_timeout
        while not self._is_mounted(mountpoint):
            if ended.is_set():
                return "exited"
            if time.monotonic() > deadline:
                return "timeout"
            time.sleep(POLL)
        return None

    @staticmethod
    def _failure(process, stderr: list[str], reason: str) -> DeltaError:
        if reason == "timeout":
            return EngineError(_("the snapshot did not open in time"))
        return error_for(process.get_exit_status(), "".join(stderr))

    def unmount(self, mountpoint: str) -> None:
        with self._lock:
            process, ended = self._process, self._ended
            self._process = None
            if process is not None:
                process.send_signal(signal.SIGTERM)
                if not ended.wait(self._stop_timeout):
                    process.force_exit()
                    ended.wait(self._stop_timeout)
            self._lazy_unmount(mountpoint)
        if self._is_mounted(mountpoint):
            raise EngineError(_("the snapshot could not be closed"))

    @staticmethod
    def _lazy_unmount(mountpoint: str) -> None:
        try:
            Gio.Subprocess.new(commands.lazy_unmount(mountpoint), Gio.SubprocessFlags.STDERR_SILENCE).wait(None)
        except GLib.Error:
            pass  # the check that follows decides whether it worked
