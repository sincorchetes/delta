"""Use cases: what was deleted from a folder since a snapshot, and putting all of it back at once."""

import os
import stat
from collections.abc import Callable

from delta.application.ports import VersionSource
from delta.application.restore_service import RestoreService
from delta.application.snapshots import snapshot_name
from delta.domain.file_version import FolderEntry
from delta.domain.paths import validate_in_home
from delta.domain.repository import Repository


CHANGE_LIMIT = 1000  # mirrored by the window (ui/folder_listing.SEARCH_CAP) to say when a list was cut


def top_level_deleted(
    tree: list[FolderEntry], folder: str, lstat: Callable[[str], os.stat_result] = os.lstat
) -> list[FolderEntry]:
    """What `tree` (everything below `folder` in a snapshot) held that is gone from the disk now.

    A deleted folder is one item, with all it held added up in its size, and what was inside it is
    not listed again. Something that exists today under the same name is never "deleted", even if
    it is a different kind of thing: restoring would have to overwrite it.
    """
    totals: dict[str, int] = {}
    deleted: list[FolderEntry] = []
    gone_folders: list[str] = []  # each ends with "/", so "a/" never catches "ab"
    for entry in sorted(tree, key=lambda e: e.name):  # a folder sorts before what is inside it
        inside = next((g for g in gone_folders if entry.name.startswith(g)), None)
        if inside is not None:
            if not entry.is_dir:
                totals[inside] += entry.size
            continue
        if not _is_gone(os.path.join(folder, entry.name), lstat):
            continue
        deleted.append(entry)
        if entry.is_dir:
            gone_folders.append(entry.name + "/")
            totals[entry.name + "/"] = 0
    return [
        FolderEntry(e.name, e.is_dir, totals[e.name + "/"] if e.is_dir else e.size, e.mtime) for e in deleted
    ]


def top_level_changed(
    tree: list[FolderEntry], folder: str, lstat: Callable[[str], os.stat_result] = os.lstat
) -> list[FolderEntry]:
    """Everything below `folder` that is not as the snapshot had it: what `top_level_deleted` finds,
    plus each file whose size or time differs today (or that is a folder now).

    Compared file by file, never by a total per folder, so there is no way to be wrong about a
    folder. Links are not judged (their size is not what borg lists) and neither is what cannot
    be read. A deleted folder is one item and what it held is not repeated.
    """
    gone = top_level_deleted(tree, folder, lstat)
    covered = {entry.name for entry in gone}
    gone_folders = [entry.name + "/" for entry in gone if entry.is_dir]
    changed = list(gone)
    for entry in tree:
        if entry.is_dir or entry.name in covered or any(entry.name.startswith(g) for g in gone_folders):
            continue
        try:
            now = lstat(os.path.join(folder, entry.name))
        except OSError:
            continue  # gone is `gone`'s business; the rest cannot be told
        if stat.S_ISLNK(now.st_mode):
            continue
        if stat.S_ISDIR(now.st_mode) or now.st_size != entry.size or int(now.st_mtime) != int(entry.mtime.timestamp()):
            changed.append(entry)
    return sorted(changed, key=lambda entry: entry.name)


def _is_gone(path: str, lstat: Callable[[str], os.stat_result]) -> bool:
    try:
        lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return True
    except OSError:
        return False  # cannot tell (permissions): never treat it as deleted
    return False


class DeletedService:
    def __init__(
        self,
        engine: VersionSource,
        repo: Repository | None,
        home: str,
        restore: RestoreService,
        lstat: Callable[[str], os.stat_result] = os.lstat,
    ) -> None:
        self._engine, self._repo, self._home = engine, repo, home
        self._restore, self._lstat = restore, lstat

    def prepare(self, folder: str) -> str:
        """Cheap synchronous validation: only folders inside the home folder have anything to restore."""
        return validate_in_home(folder, self._home)

    def find(self, snapshot: str, folder: str) -> list[FolderEntry]:
        """What the folder held in `snapshot` that is gone now; names are relative to `folder`.

        Empty without a repository. Raises InvalidPath, or SnapshotNotFound.
        """
        folder, tree = self._tree(snapshot, folder)
        return top_level_deleted(tree, folder, self._lstat)

    def find_changed(self, snapshot: str, folder: str) -> list[FolderEntry]:
        """Like `find`, plus every file that differs from what it is today at any depth.

        The first `CHANGE_LIMIT` by name: more than that is not something to read in a list.
        """
        folder, tree = self._tree(snapshot, folder)
        return top_level_changed(tree, folder, self._lstat)[:CHANGE_LIMIT]

    def _tree(self, snapshot: str, folder: str) -> tuple[str, list[FolderEntry]]:
        folder = validate_in_home(folder, self._home)
        if self._repo is None:
            return folder, []
        name = snapshot_name(self._engine, self._repo, snapshot)
        return folder, self._engine.list_tree(self._repo, name, folder)

    def restore(self, snapshot: str, folder: str) -> int:
        """Put back everything `find` reports, under its own name, and say how many items.

        The deleted set is worked out again here, not taken from an earlier look: it may have
        changed since, and nothing that exists now is ever overwritten.
        """
        folder = validate_in_home(folder, self._home)
        paths = [os.path.join(folder, entry.name) for entry in self.find(snapshot, folder)]
        return len(self._restore.place_missing(snapshot, paths))
