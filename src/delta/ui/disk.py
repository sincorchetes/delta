"""The real filesystem behind the wizard's `Inspect` hook."""

import os

from delta.ui.wizard import PathState


# Where the desktop mounts drives: nothing lives here that is not a mount, so a place that is not is a drive that is away.
MOUNT_ROOTS = ("/run/media", "/media")
BORG_README = "This is a Borg Backup repository"


def is_unmounted(path: str, is_mount=os.path.ismount) -> bool:
    for root in MOUNT_ROOTS:
        if path.startswith(root + "/"):
            parts = path[len(root) + 1 :].split("/")
            return not any(is_mount(f"{root}/{'/'.join(parts[: depth + 1])}") for depth in range(len(parts)))
    return False


def is_repository(path: str) -> bool:
    try:
        with open(os.path.join(path, "README"), encoding="utf-8", errors="replace") as readme:
            return BORG_README in readme.read(200) and os.path.isdir(os.path.join(path, "data"))
    except OSError:
        return False


def inspect_path(path: str) -> PathState:
    if is_unmounted(path):
        return PathState.UNMOUNTED
    if not os.path.lexists(path):
        return PathState.MISSING
    if not os.path.isdir(path):
        return PathState.FILE
    if is_repository(path):
        return PathState.REPOSITORY
    try:
        with os.scandir(path) as entries:
            return PathState.NOT_EMPTY if any(True for _entry in entries) else PathState.EMPTY_DIR
    except OSError:
        return PathState.NOT_EMPTY  # unreadable: certainly not a place to create a repository
