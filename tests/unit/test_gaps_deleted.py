"""What a mutation run showed nothing watched in finding what was deleted or changed."""

import stat
from datetime import datetime
from types import SimpleNamespace

from delta.application.deleted_service import DeletedService, top_level_changed, top_level_deleted
from delta.application.restore_service import RestoreService
from delta.domain.file_version import FolderEntry
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot

REPO = Repository("/srv/repo")
WHEN = datetime(2026, 1, 2, 3, 4, 5)


# --- what was deleted, with a pretend disk -----------------------------------------------------------


def entry(name, is_dir=False, size=0, mtime=WHEN):
    return FolderEntry(name, is_dir, size, mtime)


class Disk:
    """lstat of a pretend disk: what is not listed is gone; an exception listed is raised."""

    def __init__(self, folder, **present):
        self.folder, self.present = folder, {f"{folder}/{name.replace('__', '/')}": value for name, value in present.items()}

    def __call__(self, path):
        value = self.present.get(path, FileNotFoundError(path))
        if isinstance(value, Exception):
            raise value
        return value


def regular(size=0, mtime=WHEN):
    return SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_size=size, st_mtime=mtime.timestamp())


FOLDER = "/home/u/docs"


def test_a_deleted_folder_is_one_item_with_everything_it_held_added_up():
    tree = [
        entry("a-kept.txt", size=1),
        entry("ghost.txt", size=2),
        entry("gone", is_dir=True),
        entry("gone/a.txt", size=5),
        entry("gone/sub", is_dir=True),
        entry("gone/sub/b.txt", size=7),
        entry("goneX.txt", size=3),  # "gone/" must not catch "goneX.txt"
    ]
    disk = Disk(FOLDER, **{"a-kept.txt": regular(1)})

    deleted = top_level_deleted(tree, FOLDER, disk)

    assert [(e.name, e.is_dir, e.size, e.mtime) for e in deleted] == [
        ("ghost.txt", False, 2, WHEN), ("gone", True, 12, WHEN), ("goneX.txt", False, 3, WHEN),
    ]


def test_what_cannot_be_told_is_never_called_deleted():
    disk = Disk(FOLDER, **{"locked.txt": PermissionError("no")})

    assert top_level_deleted([entry("locked.txt")], FOLDER, disk) == []


def test_changes_are_what_is_gone_plus_each_file_that_differs_and_nothing_else():
    link = SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_size=1, st_mtime=0)
    now_a_folder = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_size=0, st_mtime=WHEN.timestamp())
    tree = [
        entry("dir", is_dir=True),  # a folder that is still there is not judged
        entry("link", size=1),  # links are not judged
        entry("locked.txt", size=1),  # cannot be read
        entry("same.txt", size=4),
        entry("bigger.txt", size=4),
        entry("newer.txt", size=4),
        entry("was-a-file", size=4),
        entry("ghost.txt", size=2),
        entry("gone", is_dir=True),
        entry("gone/inside.txt", size=3),  # what a deleted folder held is not repeated
        entry("gonedir-lookalike.txt", size=4),
    ]
    disk = Disk(
        FOLDER,
        dir=now_a_folder,
        link=link,
        **{
            "locked.txt": PermissionError("no"),
            "same.txt": regular(4),
            "bigger.txt": regular(5),
            "newer.txt": regular(4, datetime(2026, 6, 1)),
            "was-a-file": now_a_folder,
            "gonedir-lookalike.txt": regular(4),
        },
    )

    changed = top_level_changed(tree, FOLDER, disk)

    assert [e.name for e in changed] == ["bigger.txt", "ghost.txt", "gone", "newer.txt", "was-a-file"]


def test_the_service_asks_the_disk_through_its_own_lstat():
    asked = []

    def lstat(path):
        asked.append(path)
        raise FileNotFoundError(path)

    class Engine:
        def list_snapshots(self, repo):
            return [Snapshot("id1", "first", WHEN)]

        def list_tree(self, repo, name, folder):
            return [entry("ghost.txt", size=2)]

    service = DeletedService(Engine(), REPO, "/home/u", RestoreService(Engine(), REPO, "/home/u"), lstat=lstat)

    assert [e.name for e in service.find_changed("first", FOLDER)] == ["ghost.txt"] and asked
