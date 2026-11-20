"""The place of the repository, looked at in the file system."""

import os
from collections.abc import Callable

from delta.domain.destination import IGNORED_ENTRIES, DestinationState
from delta.domain.repository import Repository
from delta.infrastructure.drive_mounts import drive_mounted

MIB = 1024 * 1024
FULL_BELOW = MIB  # with less room than this, nothing can be backed up
FULL_AFTER_OUT_OF_SPACE = 256 * MIB  # the engine said there was no room: it is the destination if it is this short of it


class LocalDestination:
    def __init__(
        self, statvfs: Callable = os.statvfs, access: Callable = os.access, is_mount: Callable = os.path.ismount
    ) -> None:
        self._statvfs, self._access, self._is_mount = statvfs, access, is_mount

    def _absent(self, location: str, state: DestinationState) -> DestinationState:
        """MISSING or EMPTY, unless the drive is there: then it is another one, which does not hold the backups."""
        return DestinationState.OTHER_DRIVE if drive_mounted(location, self._is_mount) else state

    def state(self, repo: Repository, out_of_space: bool = False) -> DestinationState:
        """Why the folder cannot be used for a backup, or AVAILABLE.

        `out_of_space` is that the engine has just said that a disk has no room: that disk may be the home folder (where it keeps
        its cache) and not the destination, so it only counts as the destination's if this one is really short of room.
        A folder that cannot be listed for another reason counts as available: the engine will say what it makes of it.
        """
        location = repo.location
        if not os.path.isdir(location):
            return self._absent(location, DestinationState.MISSING)
        try:
            with os.scandir(location) as entries:
                if all(entry.name in IGNORED_ENTRIES for entry in entries):
                    return self._absent(location, DestinationState.EMPTY)
        except PermissionError:
            return DestinationState.DENIED
        except OSError:
            pass
        try:
            usage = self._statvfs(location)
        except OSError:
            usage = None
        if usage is not None and usage.f_flag & os.ST_RDONLY:
            return DestinationState.READ_ONLY
        if not self._access(location, os.W_OK | os.X_OK):
            return DestinationState.DENIED
        if usage is not None and usage.f_bavail * usage.f_frsize < (FULL_AFTER_OUT_OF_SPACE if out_of_space else FULL_BELOW):
            return DestinationState.FULL
        return DestinationState.AVAILABLE
