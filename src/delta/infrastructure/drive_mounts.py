"""Where the desktop mounts drives, and whether the one a path is on is mounted."""

import os
from collections.abc import Callable

# Nothing lives here that is not a mount, so a place here that is not on one is a drive that is away.
MOUNT_ROOTS = ("/run/media", "/media")


def drive_mounted(path: str, is_mount: Callable[[str], bool] = os.path.ismount) -> bool | None:
    """Whether the drive `path` is on is mounted: None when `path` is not in a place where drives are mounted."""
    for root in MOUNT_ROOTS:
        if path.startswith(root + "/"):
            parts = path[len(root) + 1 :].split("/")
            return any(is_mount(f"{root}/{'/'.join(parts[: depth + 1])}") for depth in range(len(parts)))
    return None
