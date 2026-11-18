"""The rows of a folder as it was in one version, and how each compares with now. No GTK, no D-Bus."""

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from delta.i18n import _
from delta.ui.versions import format_size


SEARCH_CAP = 1000  # what the daemon returns at most (application/version_service.SEARCH_LIMIT)


class Change(Enum):
    """How an entry of the backup compares with what is on disk today."""

    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    DELETED = "deleted"
    INSIDE = "inside"  # a folder that is still there, with something changed below it
    UNKNOWN = "unknown"  # not worth (or not possible) to tell: a folder that is still there


class Show(Enum):
    ALL = "all"
    CHANGED = "changed"  # modified or deleted
    DELETED = "deleted"


@dataclass(frozen=True)
class FolderRow:
    name: str  # in a search, the path relative to the folder that was opened
    is_dir: bool
    size: int
    mtime: int
    detail: str  # what the row says under its name
    change: Change = Change.UNKNOWN


def classify(is_dir: bool, size: int, mtime: int, current: os.stat_result | None) -> Change:
    """`current` is what lstat says about the same path today, or None if it is gone.

    A folder that still exists is UNKNOWN: telling whether anything inside changed would mean
    walking all of it, which is not worth doing for a listing.
    """
    if current is None:
        return Change.DELETED
    if stat.S_ISLNK(current.st_mode):
        return Change.UNKNOWN  # a link's size is not what borg lists: comparing them would always differ
    now_a_folder = stat.S_ISDIR(current.st_mode)
    if is_dir:
        return Change.UNKNOWN if now_a_folder else Change.MODIFIED
    if now_a_folder:
        return Change.MODIFIED
    same = current.st_size == size and int(current.st_mtime) == mtime
    return Change.UNCHANGED if same else Change.MODIFIED


def _current(path: str, lstat: Callable[[str], os.stat_result]) -> tuple[bool, os.stat_result | None]:
    """(known, stat): known is False when the disk could not be asked (permissions, say)."""
    try:
        return True, lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return True, None
    except OSError:
        return False, None


def inside_names(changes: list[dict]) -> set[str]:
    """The folders directly below the one being listed that have a change somewhere under them,
    from the changes found anywhere below it (names relative to it)."""
    return {change["name"].split("/", 1)[0] for change in changes if "/" in change["name"]}


def build_folder_rows(
    rows: list[dict],
    base: str | None = None,
    lstat: Callable[[str], os.stat_result] = os.lstat,
    dir_sizes: bool = True,
    inside: set[str] | None = None,
) -> list[FolderRow]:
    """Folders first, then by name. With `base` (the folder these rows are in, as it is today)
    each row is compared with the disk. `dir_sizes` is False for search hits, whose folders
    carry no total. `inside` names the folders that are still there but changed below."""
    ordered = sorted(rows, key=lambda row: (not row["is_dir"], row["name"].casefold(), row["name"]))
    built = []
    for row in ordered:
        change = Change.UNKNOWN
        if base is not None:
            known, current = _current(join_path(base, row["name"]), lstat)
            if known:
                change = classify(row["is_dir"], row["size"], row["mtime"], current)
        if change is Change.UNKNOWN and row["is_dir"] and inside and row["name"] in inside:
            change = Change.INSIDE
        built.append(
            FolderRow(
                name=row["name"],
                is_dir=row["is_dir"],
                size=row["size"],
                mtime=row["mtime"],
                detail=_row_detail(row, show_size=dir_sizes or not row["is_dir"]),
                change=change,
            )
        )
    return built


def apply_filter(rows: list[FolderRow], query: str, show: Show) -> list[FolderRow]:
    """Only what matches the name typed and the kind of change asked for.

    Folders that are still there stay listed whatever the filter says: they are the way in to
    what may have changed inside them.
    """
    needle = query.strip().casefold()
    kept = []
    for row in rows:
        if needle and needle not in row.name.casefold():
            continue
        if show is Show.ALL or (row.is_dir and row.change is Change.UNKNOWN):
            kept.append(row)
        elif show is Show.DELETED and row.change is Change.DELETED:
            kept.append(row)
        elif show is Show.CHANGED and row.change in (Change.DELETED, Change.MODIFIED, Change.INSIDE):
            kept.append(row)
    return kept


def _row_detail(row: dict, show_size: bool = True) -> str:
    saved = f"{datetime.fromtimestamp(row['mtime']):%Y-%m-%d  %H:%M}"
    if not show_size:
        return saved
    return _("{size} · {when}").format(size=format_size(row["size"]), when=saved)


def row_titles(entry: FolderRow) -> tuple[str, str]:
    """(title, subtitle). A search hit is named by its own name, with the folder it is in."""
    folder, name = os.path.split(entry.name)
    if not folder:
        return name, entry.detail
    return name, f"{folder}  ·  {entry.detail}"


def empty_message(searching: bool, filtered: bool) -> tuple[str, str, str]:
    """(title, detail, icon) for a listing with nothing in it, saying why."""
    if searching:
        return _("Nothing found"), _("No name here has what you typed."), "system-search-symbolic"
    if filtered:
        return _("Nothing to show"), _("Nothing in this folder changed in the way you chose."), "folder-symbolic"
    return _("This folder was empty"), "", "folder-symbolic"


def change_label(change: Change) -> str:
    """The small tag shown on a row; empty when there is nothing worth saying."""
    return {
        Change.DELETED: _("Deleted"),
        Change.MODIFIED: _("Modified"),
        Change.INSIDE: _("Changed inside"),
        Change.UNCHANGED: _("Unchanged"),
    }.get(change, "")


def join_path(folder: str, name: str) -> str:
    return folder.rstrip("/") + "/" + name


def inside_root(folder: str, root: str) -> bool:
    """Navigation never leaves the folder that was opened."""
    return folder == root or folder.startswith(root.rstrip("/") + "/")
