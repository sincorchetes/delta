"""Paths handed to borg and the scratch folders around it: details a mutation run found unwatched."""

import json
import os
import shutil
import stat
from datetime import datetime
from types import SimpleNamespace

import pytest

from delta.application import preview_service
from delta.application.deleted_service import top_level_changed
from delta.application.preview_service import PreviewService
from delta.application.restore_service import RestoreService
from delta.domain.errors import SnapshotNotFound
from delta.domain.file_version import FileEntry, FolderEntry
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot
from delta.infrastructure import borg_commands as commands
from delta.infrastructure import borg_parsing as parsing

REPO = Repository("/srv/repo")
STAMP = "2026-01-02T03:04:05.000000"
WHEN = datetime(2026, 1, 2, 3, 4, 5)


class Engine:
    """Unpacks an empty file for each path asked for."""

    def list_snapshots(self, repo):
        return [Snapshot("id1", "first", WHEN)]

    def extract(self, repo, snapshot, paths, destination):
        for path in paths:
            target = os.path.join(destination, path.lstrip("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            open(target, "w").close()


class Vandal(Engine):
    """Removes the scratch folder it was told to unpack into."""

    def extract(self, repo, snapshot, paths, destination):
        shutil.rmtree(destination)


# --- only the leading slash of a path is trimmed: a folder may be called "Xfiles" --------------------


def line(path, kind="-", **fields):
    return json.dumps({"path": path, "type": kind, "mtime": STAMP, **fields})


def test_borg_is_asked_for_a_path_minus_its_leading_slash_only():
    assert commands.list_path(REPO, "a", "/Xfiles/a")[-1] == "Xfiles/a"
    assert commands.extract(REPO, "a", ("/Xfiles/a",))[-1] == "Xfiles/a"


def test_what_borg_lists_is_matched_against_the_path_minus_its_leading_slash_only():
    stdout = line("Xfiles/a", size=3)

    assert parsing.parse_file_entry(stdout, "/Xfiles/a") == FileEntry(3, WHEN)
    assert parsing.parse_folder_listing(stdout, "/Xfiles") == [FolderEntry("a", False, 3, WHEN)]
    assert parsing.parse_folder_tree(stdout, "/Xfiles") == [FolderEntry("a", False, 3, WHEN)]
    assert parsing.parse_folder_search(stdout, "/Xfiles", "a", 10) == [FolderEntry("a", False, 3, WHEN)]


def test_a_preview_is_found_where_borg_unpacked_it(tmp_path):
    previews = PreviewService(Engine(), REPO, "/Xhome", str(tmp_path / "preview"))

    unpacked = previews.preview("first", "/Xhome/a.txt")

    assert unpacked.endswith("/Xhome/a.txt") and os.path.isfile(unpacked)
    previews.clear()


def moved_to(real_home):
    """Resolves the pretend home folder "/Xhome" to a real one, as a symlink would."""
    return lambda path: str(real_home) + path[len("/Xhome"):] if path.startswith("/Xhome") else path


def test_a_restored_copy_is_found_where_borg_unpacked_it(tmp_path):
    (tmp_path / "docs").mkdir()
    restore = RestoreService(Engine(), REPO, "/Xhome", resolve=moved_to(tmp_path), clock=lambda: WHEN)

    placed = restore.restore_beside("first", "/Xhome/docs/a.txt", replace=False)

    assert placed == str(tmp_path / "docs" / "a (restored 2026-01-02).txt") and os.path.isfile(placed)


def test_what_was_deleted_is_found_where_borg_unpacked_it(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    moves = []
    monkeypatch.setattr(shutil, "move", lambda source, destination: moves.append((source, destination)))
    restore = RestoreService(Engine(), REPO, "/Xhome", resolve=moved_to(tmp_path))

    assert restore.place_missing("first", ["/Xhome/docs/b.txt"]) == ["/Xhome/docs/b.txt"]
    assert [(source.endswith("/Xhome/docs/b.txt"), destination) for source, destination in moves] == [
        (True, "/Xhome/docs/b.txt"),
    ]


# --- a scratch folder that is already gone is not a problem of its own -------------------------------


def test_a_scratch_folder_that_vanished_does_not_hide_what_went_wrong(tmp_path):
    source = str(tmp_path / "a.txt")
    restore = RestoreService(Vandal(), REPO, str(tmp_path))
    previews = PreviewService(Vandal(), REPO, str(tmp_path), str(tmp_path / "preview"))

    with pytest.raises(SnapshotNotFound):
        restore.restore_beside("first", source, replace=False)
    with pytest.raises(SnapshotNotFound):
        previews.preview("first", source)


def test_a_scratch_folder_that_vanished_just_means_nothing_was_put_back(tmp_path):
    restore = RestoreService(Vandal(), REPO, str(tmp_path))

    assert restore.place_missing("first", [str(tmp_path / "a.txt")]) == []


# --- previews: closed from the inside out, and never opened to anyone else ---------------------------


def test_a_preview_is_closed_at_every_depth(tmp_path):
    top = tmp_path / "top"
    (top / "sub").mkdir(parents=True)
    (top / "sub" / "file").write_text("x")

    preview_service._make_read_only(str(top))

    modes = [stat.S_IMODE(os.stat(path).st_mode) for path in (top, top / "sub", top / "sub" / "file")]
    assert all(mode & preview_service.WRITE_BITS == 0 for mode in modes)
    preview_service._remove(str(top))


def test_a_preview_is_opened_to_its_owner_alone_to_be_removed(tmp_path, monkeypatch):
    previews = PreviewService(Engine(), REPO, str(tmp_path), str(tmp_path / "preview"))
    previews.preview("first", str(tmp_path / "a.txt"))
    modes, rmtree = [], shutil.rmtree

    def removing(path, **options):
        modes.append(stat.S_IMODE(os.stat(path).st_mode))
        rmtree(path, **options)

    monkeypatch.setattr(shutil, "rmtree", removing)

    previews.clear()

    assert modes == [0o700] and os.listdir(tmp_path / "preview") == []


# --- what comes back while looking for what changed --------------------------------------------------


def test_what_reappears_while_looking_is_still_listed_once_and_a_deleted_folder_stays_one_item():
    tree = [
        FolderEntry("ghost.txt", False, 2, WHEN),
        FolderEntry("gone", True, 0, WHEN),
        FolderEntry("gone/inside.txt", False, 3, WHEN),
    ]
    asked = set()

    def lstat(path):
        if path not in asked and not path.endswith("inside.txt"):
            asked.add(path)
            raise FileNotFoundError(path)
        return SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_size=99, st_mtime=0)

    assert [entry.name for entry in top_level_changed(tree, "/home/u/docs", lstat)] == ["ghost.txt", "gone"]
