"""BackupEngine implementation that drives the borg CLI via Gio.Subprocess."""

import os
import signal
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from delta.application.ports import SecretStore
from delta.domain.backup_job import BackupJob
from delta.domain.errors import BackupInterrupted, BackupWarning, EngineError, PassphraseError
from delta.domain.file_version import FileEntry, FolderEntry
from delta.domain.progress import ProgressEvent
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy
from delta.domain.snapshot import Snapshot
from delta.i18n import _
from delta.infrastructure import borg_commands as commands
from delta.infrastructure.listing_cache import ListingCache
from delta.infrastructure.borg_parsing import (
    error_for,
    parse_file_entry,
    parse_folder_listing,
    parse_folder_search,
    parse_folder_tree,
    parse_progress,
    parse_repository_id,
    parse_snapshots,
)


PASSPHRASE_FD = 3
SNAPSHOTS_TTL = 60.0  # seconds a list of snapshots is trusted, should something else have changed the repository
INSIST_AFTER = 5.0  # seconds borg gets to stop at one SIGINT before a second one cuts it short
BORG_WARNING_EXIT = 1  # borg: archive created, but with warnings
PASSPHRASE_SOURCES = frozenset({"BORG_PASSPHRASE", "BORG_PASSCOMMAND"})
# Inherited from the user's shell, these would silently beat the keyring passphrase.
AMBIENT_PASSPHRASE_VARS = (
    "BORG_PASSPHRASE",
    "BORG_PASSCOMMAND",
    "BORG_NEW_PASSPHRASE",
    "BORG_NEW_PASSCOMMAND",
)


class BorgRunner:
    def __init__(
        self,
        env: dict[str, str] | None = None,
        binary: str = "borg",
        secrets: SecretStore | None = None,
        clock: Callable[[], float] = time.monotonic,
        insist_after: float = INSIST_AFTER,
    ) -> None:
        self._insist_after = insist_after
        self._env = env or {}
        self._binary = binary
        self._secrets = secrets
        self._clock = clock
        self._lock = threading.Lock()
        self._listings = ListingCache()
        self._snapshot_lists: dict[str, tuple[float, list[Snapshot]]] = {}  # repository -> (when, snapshots)
        self._running: set = set()  # the borg processes alive now (a backup and reads can overlap)
        self._interrupted: set = set()  # those `interrupt` signalled, so their failure is a stop, not an error

    def init(self, repo: Repository) -> None:
        self._ensure_parent(Path(repo.location))
        self._run(commands.init(repo), repo)
        self._forget_snapshots(repo)

    @staticmethod
    def _ensure_parent(location: Path) -> None:
        """borg only creates the repository directory itself, not its parents."""
        try:
            location.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as err:
            raise EngineError(_("cannot create {folder}: {reason}").format(folder=location.parent, reason=err.strerror)) from err

    def create(
        self,
        repo: Repository,
        job: BackupJob,
        name: str | None = None,
        on_progress: Callable[[ProgressEvent], None] | None = None,
    ) -> str:
        archive = name or f"{datetime.now():%Y-%m-%dT%H-%M-%S}-{uuid.uuid4().hex[:6]}"
        try:
            self._run(commands.create(repo, archive, job), repo, on_progress=on_progress)
        except EngineError as err:
            if err.returncode == BORG_WARNING_EXIT:
                raise BackupWarning(str(err)) from err
            raise
        finally:
            self._forget_snapshots(repo)  # even a failed one may have left a partial archive
        return archive

    def break_lock(self, repo: Repository) -> None:
        self._run(commands.break_lock(repo), repo)

    def list_snapshots(self, repo: Repository) -> list[Snapshot]:
        """The repository's snapshots, newest last. Asked of borg at most once a minute: every other
        question starts by turning a snapshot id into its name, and the list only changes when this
        engine makes or prunes one (which forgets it). Also what keeps the windows working while a
        backup holds the repository, when `borg list` would have to wait."""
        now = self._clock()
        with self._lock:
            kept = self._snapshot_lists.get(repo.location)
        if kept is not None and now - kept[0] < SNAPSHOTS_TTL:
            return list(kept[1])
        snapshots = parse_snapshots(self._run(commands.list_archives(repo), repo))
        with self._lock:
            self._snapshot_lists[repo.location] = (now, snapshots)
        return list(snapshots)

    def repository_id(self, repo: Repository) -> str:
        return parse_repository_id(self._run(commands.repository_id(repo), repo))

    def _forget_snapshots(self, repo: Repository) -> None:
        with self._lock:
            self._snapshot_lists.pop(repo.location, None)

    def _listing(self, repo: Repository, snapshot: str, path: str) -> str:
        """`borg list` of a path, asked of borg only the first time (see `ListingCache`)."""
        cached = self._listings.get(repo.location, snapshot, path)
        if cached is not None:
            return cached
        listing = self._run(commands.list_path(repo, snapshot, path), repo)
        self._listings.put(repo.location, snapshot, path, listing)
        return listing

    def file_entry(self, repo: Repository, snapshot: str, path: str) -> FileEntry | None:
        return parse_file_entry(self._listing(repo, snapshot, path), path)

    def list_folder(self, repo: Repository, snapshot: str, path: str) -> list[FolderEntry]:
        return parse_folder_listing(self._listing(repo, snapshot, path), path)

    def list_tree(self, repo: Repository, snapshot: str, path: str) -> list[FolderEntry]:
        return parse_folder_tree(self._listing(repo, snapshot, path), path)

    def search_folder(
        self, repo: Repository, snapshot: str, path: str, query: str, limit: int
    ) -> list[FolderEntry]:
        return parse_folder_search(self._listing(repo, snapshot, path), path, query, limit)

    def extract(
        self, repo: Repository, snapshot: str, paths: tuple[str, ...], destination: str
    ) -> None:
        self._run(commands.extract(repo, snapshot, paths), repo, cwd=destination)

    def prune(self, repo: Repository, policy: RetentionPolicy) -> None:
        try:
            self._run(commands.prune(repo, policy), repo)
        finally:
            self._forget_snapshots(repo)

    def _run(
        self,
        argv: list[str],
        repo: Repository,
        cwd: str | None = None,
        on_progress: Callable[[ProgressEvent], None] | None = None,
    ) -> str:
        argv = [self._binary, *argv[1:]]
        launcher = self.launcher(repo, cwd)
        try:
            process = launcher.spawnv(argv)
        except GLib.Error as err:
            raise EngineError(_("cannot run {program}: {reason}").format(program=self._binary, reason=err.message)) from err
        self._track(process)
        try:
            if on_progress is None:
                _status, stdout, stderr = process.communicate_utf8(None, None)
            else:
                stdout, stderr = self._stream(process, on_progress)
        except GLib.Error as err:
            raise EngineError(_("cannot run {program}: {reason}").format(program=self._binary, reason=err.message)) from err
        finally:
            interrupted = self._untrack(process)
        if not process.get_successful():
            if interrupted:
                raise BackupInterrupted(_("stopped on request"))
            raise error_for(process.get_exit_status(), stderr or "")
        return stdout or ""

    def launcher(
        self,
        repo: Repository,
        cwd: str | None = None,
        flags: Gio.SubprocessFlags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
    ):
        """A launcher whose environment holds exactly what borg may see."""
        launcher = Gio.SubprocessLauncher.new(flags)
        if self._secrets is not None:
            for variable in AMBIENT_PASSPHRASE_VARS:
                launcher.unsetenv(variable)
        for key, value in self._env.items():
            launcher.setenv(key, value, True)
        self._pass_passphrase(launcher, repo)
        if cwd:
            launcher.set_cwd(cwd)
        return launcher

    def interrupt(self) -> None:
        """SIGINT makes borg exit cleanly (exit 2) and release the repository lock.

        Sent to every borg that is running, not just one: a backup and the reads the windows ask
        for run side by side, and a read finishing must never make the backup unreachable.

        One SIGINT does not stop borg in the middle of a large file, so those still alive after
        `insist_after` get a second one: borg then quits at once (exit 130), keeping its
        checkpoint and releasing the lock (scripts/verify_mount_vs_backup.sh).
        """
        with self._lock:
            stopping = list(self._running)
            self._interrupted.update(stopping)
            for process in stopping:
                process.send_signal(signal.SIGINT)
        if stopping:
            timer = threading.Timer(self._insist_after, self._insist, [stopping])
            timer.daemon = True
            timer.start()

    def _insist(self, stopping: list) -> None:
        with self._lock:
            for process in stopping:
                if process in self._running:
                    process.send_signal(signal.SIGINT)

    def _track(self, process) -> None:
        with self._lock:
            self._running.add(process)

    def _untrack(self, process) -> bool:
        """Forget a process that ended; say whether it was stopped by `interrupt`."""
        with self._lock:
            self._running.discard(process)
            was_interrupted = process in self._interrupted
            self._interrupted.discard(process)
            return was_interrupted

    def _pass_passphrase(self, launcher, repo: Repository) -> None:
        """Hand the keyring passphrase to borg over a pipe (never argv/env)."""
        if self._secrets is None:
            return
        passphrase = self._secrets.get(repo.location)
        if passphrase is None:
            if PASSPHRASE_SOURCES & self._env.keys():
                return  # a development override supplies it
            # Without this, borg would try to ask on a terminal that does not exist.
            raise PassphraseError(_("The passphrase for this repository is not in the keyring."))
        read_fd, write_fd = os.pipe()
        with os.fdopen(write_fd, "wb") as writer:
            writer.write(passphrase.encode())
        launcher.setenv("BORG_PASSPHRASE_FD", str(PASSPHRASE_FD), True)
        launcher.take_fd(read_fd, PASSPHRASE_FD)

    @staticmethod
    def _stream(process, on_progress) -> tuple[str, str]:
        """Forward stderr progress lines live; stdout (small JSON) is read afterwards."""
        err_stream = Gio.DataInputStream.new(process.get_stderr_pipe())
        stderr_lines = []
        while True:
            line, _length = err_stream.read_line_utf8(None)
            if line is None:
                break
            stderr_lines.append(line)
            event = parse_progress(line)
            if event is not None:
                on_progress(event)
        process.wait(None)
        out_stream = Gio.DataInputStream.new(process.get_stdout_pipe())
        chunks = []
        while True:
            line, _length = out_stream.read_line_utf8(None)
            if line is None:
                break
            chunks.append(line)
        return "\n".join(chunks), "\n".join(stderr_lines)
