"""Ports the application layer depends on; infrastructure implements them."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from delta.domain.backup_job import BackupJob
from delta.domain.destination import DestinationState
from delta.domain.file_version import FileEntry, FolderEntry
from delta.domain.notification import Notification
from delta.domain.progress import ProgressEvent
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy
from delta.domain.schedule import Schedule
from delta.domain.snapshot import Snapshot


class SecretStore(Protocol):
    """Keyring holding repository passphrases, keyed by repository location."""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, secret: str) -> None: ...

    def delete(self, key: str) -> None: ...


class JobJournal(Protocol):
    """Durable mark of a backup in progress, so a crash or shutdown is detected later."""

    def begin(self) -> None: ...

    def end(self) -> None: ...

    def was_interrupted(self) -> bool: ...


class Notifier(Protocol):
    """Tells the user something (desktop notification, portal, ...)."""

    def notify(self, notification: Notification) -> None: ...


class Scheduler(Protocol):
    """Runs automatic backups on a schedule (systemd timer, portal, ...)."""

    def apply(self, schedule: Schedule) -> None: ...

    def disable(self) -> None: ...

    def next_run(self) -> datetime | None:
        """When the next automatic backup is due; None when unknown or not scheduled."""
        ...


class SnapshotMounter(Protocol):
    """Shows one snapshot as a read-only folder (FUSE). Only the native install has one."""

    def mount(self, repo: Repository, snapshot: str, mountpoint: str) -> None: ...

    def unmount(self, mountpoint: str) -> None:
        """Always succeeds in leaving the folder unmounted, even with files still open in it."""
        ...


class DestinationProbe(Protocol):
    """Tells whether the place where the repository lives can be reached (a drive that is connected, a folder that is there)."""

    def state(self, repo: Repository) -> DestinationState: ...


class MountUsage(Protocol):
    """Tells which programs are still using an open snapshot folder."""

    def users(self, mountpoint: str) -> list[str]:
        """Each user as a short description; empty when nobody uses the folder."""
        ...


class SessionEvents(Protocol):
    """Tells when the computer is about to sleep or the session gets locked."""

    def watch(self, callback: Callable[[], None]) -> None: ...

    def hold(self) -> None:
        """Make the computer wait a moment before sleeping, until `release`."""
        ...

    def release(self) -> None: ...


class MountEvents(Protocol):
    """Tells when a drive or a folder gets mounted."""

    def watch(self, callback: Callable[[], None]) -> None: ...


class SnapshotSource(Protocol):
    def list_snapshots(self, repo: Repository) -> list[Snapshot]: ...


class VersionSource(SnapshotSource, Protocol):
    def file_entry(self, repo: Repository, snapshot: str, path: str) -> FileEntry | None: ...

    def list_folder(self, repo: Repository, snapshot: str, path: str) -> list[FolderEntry]: ...

    def search_folder(
        self, repo: Repository, snapshot: str, path: str, query: str, limit: int
    ) -> list[FolderEntry]: ...

    def list_tree(self, repo: Repository, snapshot: str, path: str) -> list[FolderEntry]: ...


class BackupEngine(VersionSource, Protocol):
    def init(self, repo: Repository) -> None: ...

    def create(
        self,
        repo: Repository,
        job: BackupJob,
        name: str | None = None,
        on_progress: Callable[[ProgressEvent], None] | None = None,
    ) -> str: ...

    def list_snapshots(self, repo: Repository) -> list[Snapshot]: ...

    def extract(
        self, repo: Repository, snapshot: str, paths: tuple[str, ...], destination: str
    ) -> None: ...

    def prune(self, repo: Repository, policy: RetentionPolicy) -> None: ...

    def break_lock(self, repo: Repository) -> None:
        """Remove a stale lock. Dangerous if another process really holds the repository."""
        ...

    def interrupt(self) -> None:
        """Ask a running operation to stop cleanly; it then raises BackupInterrupted."""
        ...
