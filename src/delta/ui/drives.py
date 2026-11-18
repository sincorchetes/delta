"""Removable drives the user can keep backups on. Works on Gio.Mount-like objects.

The wizard feeds it `Gio.VolumeMonitor.get().get_mounts()`; tests feed it fakes."""

import os
from collections.abc import Iterable
from dataclasses import dataclass

FOLDER_ON_DRIVE = "delta-backups"


@dataclass(frozen=True)
class Drive:
    name: str
    mount_point: str

    @property
    def suggested_folder(self) -> str:
        return os.path.join(self.mount_point, FOLDER_ON_DRIVE)


def removable_drives(mounts: Iterable) -> list[Drive]:
    """Mounted drives that can be unplugged; never the system disk."""
    found = []
    for mount in mounts:
        if mount.is_shadowed():
            continue
        volume = mount.get_volume()
        drive = volume.get_drive() if volume is not None else None
        removable = mount.can_eject() or (drive is not None and drive.is_removable())
        root = mount.get_root()
        path = root.get_path() if root is not None else None
        if removable and path:
            found.append(Drive(mount.get_name(), path))
    return found
