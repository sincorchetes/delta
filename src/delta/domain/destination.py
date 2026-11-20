"""Whether the place where the backups are kept can be reached."""

from enum import Enum


class DestinationState(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"  # the folder is not there: a drive that is not connected, or a folder that was removed
    EMPTY = "empty"  # it is there and holds nothing: the mount point of a drive that is not mounted, or a wiped one
    OTHER_DRIVE = "other-drive"  # a drive is mounted where the backups were kept, and they are not on it
    OTHER_REPOSITORY = "other-repository"  # the drive is there and holds a repository, but not the one the backups were made in
    FULL = "full"  # it is there, and there is no room left in it
    READ_ONLY = "read-only"  # mounted so that nothing can be written to it
    DENIED = "denied"  # the person has no permission to write in it

# What a file system puts in an empty drive by itself (ext4 makes `lost+found`): it does not make the drive hold anything.
IGNORED_ENTRIES = frozenset({"lost+found"})
