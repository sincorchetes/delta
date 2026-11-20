"""The real filesystem behind the wizard's `Inspect` hook."""

import os

from delta.domain.destination import IGNORED_ENTRIES
from delta.infrastructure.drive_mounts import drive_mounted
from delta.ui.wizard import PathState

BORG_README = "This is a Borg Backup repository"


def is_unmounted(path: str, is_mount=os.path.ismount) -> bool:
    return drive_mounted(path, is_mount) is False


def is_repository(path: str) -> bool:
    try:
        with open(os.path.join(path, "README"), encoding="utf-8", errors="replace") as readme:
            return BORG_README in readme.read(200) and os.path.isdir(os.path.join(path, "data"))
    except OSError:
        return False


def unwritable(path: str, statvfs=os.statvfs, access=os.access) -> PathState | None:
    """READ_ONLY or NOT_WRITABLE when a backup could not be written at `path`, or where it would be made, else None."""
    folder = path
    while not os.path.isdir(folder):
        parent = os.path.dirname(folder)
        if parent == folder:
            return None
        folder = parent
    try:
        if statvfs(folder).f_flag & os.ST_RDONLY:
            return PathState.READ_ONLY
    except OSError:
        pass
    return None if access(folder, os.W_OK | os.X_OK) else PathState.NOT_WRITABLE


def inspect_path(path: str) -> PathState:
    if is_unmounted(path):
        return PathState.UNMOUNTED
    if os.path.lexists(path) and not os.path.isdir(path):
        return PathState.FILE
    problem = unwritable(path)
    if problem is not None:
        return problem
    if not os.path.lexists(path):
        return PathState.MISSING
    if is_repository(path):
        return PathState.REPOSITORY
    try:
        with os.scandir(path) as entries:
            return PathState.EMPTY_DIR if all(entry.name in IGNORED_ENTRIES for entry in entries) else PathState.NOT_EMPTY
    except OSError:
        return PathState.NOT_EMPTY  # unreadable: certainly not a place to create a repository
