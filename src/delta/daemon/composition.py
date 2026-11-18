"""Builds the configuration-dependent services (repository, retention)."""

import logging
import os
from dataclasses import dataclass

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

from delta.application.backup_service import BackupService
from delta.application.browse_service import BrowseService
from delta.application.deleted_service import DeletedService
from delta.application.ports import BackupEngine, SnapshotMounter
from delta.application.preview_service import PreviewService
from delta.application.prune_service import PruneService
from delta.application.restore_service import RestoreService
from delta.application.snapshot_service import SnapshotService
from delta.application.unlock_service import UnlockService
from delta.application.version_service import VersionService
from delta.infrastructure.runtime import in_flatpak
from delta.infrastructure.settings import (
    configured_excludes,
    configured_repository,
    configured_retention,
    configured_sources,
)

log = logging.getLogger(__name__)

DEFAULT_EXCLUDES = (".cache", ".local/share/Trash")


@dataclass(frozen=True)
class Services:
    snapshots: SnapshotService
    backup: BackupService
    restore: RestoreService
    versions: VersionService
    prune: PruneService
    unlock: UnlockService
    preview: PreviewService
    deleted: DeletedService
    browse: BrowseService | None  # None where snapshots cannot be mounted (Flatpak)


def preview_root() -> str:
    """Volatile and private to the user: previews never reach the disk and vanish at logout.

    Not in a Flatpak: its runtime folder is a memory of the sandbox that the portals cannot hand to another
    application (the Open button would fail), so the previews go to the app's own cache folder, on the disk.
    The daemon forgets them when it starts and when it stops, and the window when it closes.
    """
    base = GLib.get_user_cache_dir() if in_flatpak() else GLib.get_user_runtime_dir()
    return os.path.join(base, "delta", "preview")


def browse_root() -> str:
    return os.path.join(GLib.get_user_runtime_dir(), "delta", "browse")


def resolve_sources(configured: tuple[str, ...], home: str) -> tuple[str, ...]:
    """Empty means the home folder. Invalid entries are dropped, never widened to $HOME.

    If the user configured folders and none is valid, the result is empty and the
    backup refuses to run, instead of silently backing up far more than intended.
    """
    if not configured:
        return (home,)
    valid = []
    for entry in configured:
        path = os.path.expanduser(entry)
        if os.path.isabs(path):
            valid.append(os.path.normpath(path))
        else:
            log.warning("ignoring backup source %r: not an absolute path", entry)
    return tuple(dict.fromkeys(valid))


def resolve_excludes(configured: tuple[str, ...], home: str) -> tuple[str, ...]:
    """Built-in exclusions plus the user's own, as borg patterns.

    The user's paths become `pp:` (literal path prefix: the path and what is inside it), so a
    folder named `*` or `[1]` can never act as a wildcard and skip more than was asked.
    """
    builtin = tuple(os.path.join(home, p) for p in DEFAULT_EXCLUDES)
    chosen = []
    for entry in configured:
        path = os.path.expanduser(entry)
        if os.path.isabs(path):
            chosen.append(f"pp:{os.path.normpath(path)}")
        else:
            log.warning("ignoring exclusion %r: not an absolute path", entry)
    return builtin + tuple(dict.fromkeys(chosen))


def build_services(engine: BackupEngine, mounter: SnapshotMounter | None = None) -> Services:
    """Read the current configuration and wire the services around it."""
    repo, home = configured_repository(), os.path.expanduser("~")
    restore = RestoreService(engine, repo, home)
    return Services(
        snapshots=SnapshotService(engine, repo),
        backup=BackupService(
            engine,
            repo,
            sources=resolve_sources(configured_sources(), home),
            excludes=resolve_excludes(configured_excludes(), home),
        ),
        restore=restore,
        versions=VersionService(engine, repo, home),
        prune=PruneService(engine, repo, configured_retention()),
        unlock=UnlockService(engine, repo),
        preview=PreviewService(engine, repo, home, preview_root()),
        deleted=DeletedService(engine, repo, home, restore),
        browse=None if mounter is None else BrowseService(engine, mounter, repo, browse_root()),
    )
