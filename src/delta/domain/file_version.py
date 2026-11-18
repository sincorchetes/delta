"""A path as it existed inside one snapshot."""

from dataclasses import dataclass
from datetime import datetime

from delta.domain.snapshot import Snapshot


@dataclass(frozen=True)
class FileEntry:
    size: int
    mtime: datetime
    is_dir: bool = False


@dataclass(frozen=True)
class FolderEntry:
    """One direct child of a folder as it was in a snapshot; a folder's size covers its contents."""

    name: str
    is_dir: bool
    size: int
    mtime: datetime


@dataclass(frozen=True)
class FileVersion:
    snapshot: Snapshot
    entry: FileEntry


def distinct_versions(versions: list[FileVersion]) -> list[FileVersion]:
    """Collapse runs of identical content (same size and mtime).

    Input oldest first; keeps the oldest snapshot of each run; returns newest first.
    """
    kept: list[FileVersion] = []
    for version in versions:
        if not kept or kept[-1].entry != version.entry:
            kept.append(version)
    return kept[::-1]
