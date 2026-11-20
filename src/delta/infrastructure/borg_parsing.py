"""Parsing of borg output and mapping of failures to domain errors."""

import json
import re
from datetime import datetime

from delta.domain.errors import (
    DeltaError,
    EngineError,
    PassphraseError,
    RepositoryLocked,
    RepositoryNotFound,
    is_lock_message,
)
from delta.domain.file_version import FileEntry, FolderEntry
from delta.domain.progress import ProgressEvent
from delta.domain.snapshot import Snapshot
from delta.i18n import _


_CHECKPOINT = re.compile(r"\.checkpoint(\.\d+)?$")


def is_checkpoint(name: str) -> bool:
    """borg's partial archives (`<name>.checkpoint[.N]`): never a restore point."""
    return _CHECKPOINT.search(name) is not None


def parse_snapshots(stdout: str) -> list[Snapshot]:
    try:
        archives = json.loads(stdout)["archives"]
        snapshots = [
            Snapshot(a["id"], a["name"], datetime.fromisoformat(a["time"]))
            for a in archives
            if not is_checkpoint(a["name"])
        ]
    except (ValueError, KeyError, TypeError) as err:
        raise EngineError(_("unexpected borg list output: {error}").format(error=err)) from err
    return sorted(snapshots, key=lambda s: s.created)


def parse_repository_id(stdout: str) -> str:
    try:
        return str(json.loads(stdout)["repository"]["id"])
    except (ValueError, KeyError, TypeError) as err:
        raise EngineError(_("unexpected borg list output: {error}").format(error=err)) from err


def parse_file_entry(stdout: str, path: str) -> FileEntry | None:
    """Entry for exactly `path` from `borg list --json-lines`, or None if absent.

    A folder's own size and mtime say little (its mtime only moves when a direct child is added
    or removed), so its entry is a fingerprint of everything below it: total size and newest mtime.
    """
    wanted = path.lstrip("/")
    prefix = wanted + "/"
    own = None
    below_size = 0
    below_newest = None
    for line in stdout.splitlines():
        try:
            data = json.loads(line)
            name = data["path"]
            if name == wanted:
                own = (data.get("type"), int(data.get("size", 0)), datetime.fromisoformat(data["mtime"]))
            elif name.startswith(prefix):
                below_size += int(data.get("size", 0))
                mtime = datetime.fromisoformat(data["mtime"])
                below_newest = mtime if below_newest is None else max(below_newest, mtime)
        except (ValueError, KeyError, TypeError) as err:
            raise EngineError(_("unexpected borg list output: {error}").format(error=err)) from err
    if own is None:
        return None
    kind, size, mtime = own
    if kind != "d":
        return FileEntry(size, mtime)
    return FileEntry(below_size, max(mtime, below_newest) if below_newest else mtime, is_dir=True)


def parse_folder_listing(stdout: str, path: str) -> list[FolderEntry]:
    """The direct children of `path` from `borg list --json-lines`, which lists everything below it.

    A child's folder-ness and size are inferred from the deeper paths too, so a folder borg
    listed no line for is still a folder, and its size is that of all it holds.
    """
    prefix = path.lstrip("/") + "/"
    children: dict[str, list] = {}  # name -> [is_dir, size, newest mtime]
    for line in stdout.splitlines():
        try:
            data = json.loads(line)
            name = data["path"]
            if not name.startswith(prefix):
                continue
            first, _separator, deeper = name[len(prefix):].partition("/")
            if not first:
                continue
            size, mtime = int(data.get("size", 0)), datetime.fromisoformat(data["mtime"])
        except (ValueError, KeyError, TypeError) as err:
            raise EngineError(_("unexpected borg list output: {error}").format(error=err)) from err
        child = children.setdefault(first, [False, 0, mtime])
        if deeper:
            child[0], child[1], child[2] = True, child[1] + size, max(child[2], mtime)
        elif data.get("type") == "d":
            child[0], child[2] = True, max(child[2], mtime)
        else:
            child[1], child[2] = size, mtime
    return [FolderEntry(name, is_dir, size, mtime) for name, (is_dir, size, mtime) in children.items()]


def parse_folder_tree(stdout: str, path: str) -> list[FolderEntry]:
    """Everything below `path`, at any depth, with names relative to it. A folder's size is 0:
    only the file entries that borg lists carry one."""
    prefix = path.lstrip("/") + "/"
    tree: list[FolderEntry] = []
    for line in stdout.splitlines():
        try:
            data = json.loads(line)
            name = data["path"]
            if not name.startswith(prefix) or name == prefix:
                continue
            tree.append(
                FolderEntry(
                    name[len(prefix):], data.get("type") == "d", int(data.get("size", 0)),
                    datetime.fromisoformat(data["mtime"]),
                )
            )
        except (ValueError, KeyError, TypeError) as err:
            raise EngineError(_("unexpected borg list output: {error}").format(error=err)) from err
    return tree


def parse_folder_search(stdout: str, path: str, query: str, limit: int) -> list[FolderEntry]:
    """Entries anywhere below `path` whose own name contains `query` (ignoring case), at most
    `limit`. Each name is the path relative to `path`. A folder's size is 0: only the file
    entries that borg lists carry one."""
    prefix = path.lstrip("/") + "/"
    needle = query.strip().casefold()
    hits: list[FolderEntry] = []
    for line in stdout.splitlines():
        try:
            data = json.loads(line)
            name = data["path"]
            if not name.startswith(prefix):
                continue
            relative = name[len(prefix):]
            if not relative or needle not in relative.rpartition("/")[2].casefold():
                continue
            hit = FolderEntry(
                relative, data.get("type") == "d", int(data.get("size", 0)), datetime.fromisoformat(data["mtime"])
            )
        except (ValueError, KeyError, TypeError) as err:
            raise EngineError(_("unexpected borg list output: {error}").format(error=err)) from err
        hits.append(hit)
        if len(hits) >= limit:
            break
    return hits


def parse_progress(line: str) -> ProgressEvent | None:
    """Return the event for a `--log-json` archive_progress line, else None."""
    try:
        data = json.loads(line)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("type") != "archive_progress" or data.get("finished"):
        return None
    return ProgressEvent(
        files=int(data.get("nfiles", 0)),
        original_size=int(data.get("original_size", 0)),
        path=str(data.get("path", "")),
    )


def log_messages(stderr: str) -> str:
    """Flatten `--log-json` stderr into plain text (plain lines pass through)."""
    lines = []
    for line in stderr.splitlines():
        # A prompt such as "Enter passphrase: " can precede the JSON on the same line.
        start = line.find('{"type"')
        try:
            data = json.loads(line[max(start, 0):])
        except ValueError:
            lines.append(line)
            continue
        if isinstance(data, dict) and data.get("type") == "log_message":
            lines.append(str(data.get("message", "")))
    return "\n".join(lines)


def error_for(returncode: int, stderr: str) -> DeltaError:
    text = log_messages(stderr).strip()
    lowered = text.lower()
    if "does not exist" in lowered or "is not a valid repository" in lowered:
        return RepositoryNotFound(text)
    if is_lock_message(text):
        return RepositoryLocked(text)
    if "passphrase" in lowered and ("incorrect" in lowered or "wrong" in lowered):
        return PassphraseError(text)
    return EngineError(text or f"borg exited with status {returncode}", returncode)
