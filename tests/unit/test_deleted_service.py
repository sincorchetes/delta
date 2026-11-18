import os
import stat
from datetime import datetime

import pytest

from delta.application.deleted_service import CHANGE_LIMIT, DeletedService, top_level_changed, top_level_deleted
from delta.domain.errors import InvalidPath, SnapshotNotFound
from delta.domain.file_version import FolderEntry
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot

WHEN = datetime(2026, 1, 1)
FOLDER = "/home/u/Pictures"


def file(name, size=1):
    return FolderEntry(name, False, size, WHEN)


def folder(name):
    return FolderEntry(name, True, 0, WHEN)


def disk(*present, broken=()):
    """A pretend disk: only `present` paths exist; `broken` ones cannot be asked about."""

    def lstat(path):
        if path in broken:
            raise PermissionError(path)
        if path not in present:
            raise FileNotFoundError(path)
        return os.stat_result((stat.S_IFREG | 0o644, 0, 0, 1, 0, 0, 0, 0, 0, 0))

    return lstat


def names(items):
    return [item.name for item in items]


def gone(tree, *present, **kw):
    return top_level_deleted(tree, FOLDER, disk(*present, **kw))


def test_a_file_that_is_gone_is_reported_and_one_that_is_there_is_not():
    tree = [file("a.png"), file("b.png")]
    assert names(gone(tree, FOLDER + "/b.png")) == ["a.png"]


def test_a_deleted_folder_is_one_item_with_all_it_held_added_up():
    tree = [folder("trip"), file("trip/1.jpg", 10), folder("trip/raw"), file("trip/raw/2.nef", 100), file("keep.txt")]

    (item,) = gone(tree, FOLDER + "/keep.txt")

    assert (item.name, item.is_dir, item.size) == ("trip", True, 110)


def test_what_was_inside_a_deleted_folder_is_not_listed_again():
    tree = [folder("trip"), file("trip/1.jpg"), file("trip/2.jpg")]
    assert names(gone(tree)) == ["trip"]


def test_a_deleted_file_inside_a_folder_that_still_exists_is_found_on_its_own():
    tree = [folder("trip"), file("trip/1.jpg"), file("trip/2.jpg")]
    assert names(gone(tree, FOLDER + "/trip", FOLDER + "/trip/2.jpg")) == ["trip/1.jpg"]


def test_a_deleted_folder_does_not_swallow_a_sibling_whose_name_starts_the_same():
    tree = [folder("a"), file("a/x"), file("ab"), folder("a b")]
    assert names(gone(tree, FOLDER + "/ab", FOLDER + "/a b")) == ["a"]


def test_a_different_kind_of_thing_under_the_same_name_is_not_deleted():
    """Restoring would have to overwrite it, and this never overwrites."""
    assert gone([folder("notes")], FOLDER + "/notes") == []
    assert gone([file("notes")], FOLDER + "/notes") == []


def test_when_the_disk_cannot_be_asked_nothing_is_called_deleted():
    assert gone([file("secret.txt")], broken=(FOLDER + "/secret.txt",)) == []


def test_everything_present_means_nothing_to_restore():
    tree = [folder("trip"), file("trip/1.jpg")]
    assert gone(tree, FOLDER + "/trip", FOLDER + "/trip/1.jpg") == []


def test_the_order_does_not_matter_and_the_result_is_in_name_order():
    tree = [file("trip/1.jpg"), file("z.txt"), folder("trip"), file("a.txt")]
    assert names(gone(tree)) == ["a.txt", "trip", "z.txt"]


def test_a_file_whose_folder_entry_borg_did_not_list_is_still_found():
    assert names(gone([file("lost/1.jpg"), file("lost/2.jpg")])) == ["lost/1.jpg", "lost/2.jpg"]


# --- the service ------------------------------------------------------------------------------

HOME = "/home/u"


class FakeEngine:
    def __init__(self, tree):
        self.tree, self.asked = tree, []

    def list_snapshots(self, repo):
        return [Snapshot("id1", "first", WHEN)]

    def list_tree(self, repo, snapshot, path):
        self.asked.append((snapshot, path))
        return self.tree


class FakeRestore:
    def __init__(self):
        self.placed = None

    def place_missing(self, snapshot, sources):
        self.placed = (snapshot, sources)
        return sources


def service(tree, repo=Repository("/r"), lstat=None):
    engine, restore = FakeEngine(tree), FakeRestore()
    return DeletedService(engine, repo, HOME, restore, lstat=lstat or disk()), engine, restore


def test_find_lists_what_is_gone_using_the_snapshots_name():
    deleted, engine, _ = service([file("a.png")])
    assert names(deleted.find("id1", FOLDER)) == ["a.png"]
    assert engine.asked == [("first", FOLDER)]


def test_restore_puts_back_the_top_level_items_by_full_path_and_counts_them():
    deleted, _, restore = service([folder("trip"), file("trip/1.jpg"), file("a.png")])

    count = deleted.restore("first", FOLDER)

    assert count == 2
    assert restore.placed == ("first", [FOLDER + "/a.png", FOLDER + "/trip"])


def test_restore_with_nothing_deleted_does_nothing():
    deleted, _, restore = service([file("a.png")], lstat=disk(FOLDER + "/a.png"))
    assert deleted.restore("first", FOLDER) == 0
    assert restore.placed == ("first", [])


def test_an_unknown_snapshot_is_refused():
    with pytest.raises(SnapshotNotFound):
        service([])[0].find("nope", FOLDER)


@pytest.mark.parametrize("outside", ["/etc", "/home/u/../x", "relative"])
def test_only_folders_inside_home_are_looked_at(outside):
    with pytest.raises(InvalidPath):
        service([])[0].find("first", outside)


def test_without_a_repository_nothing_is_found_or_restored():
    deleted, _, restore = service([file("a.png")], repo=None)
    assert deleted.find("first", FOLDER) == []
    assert deleted.restore("first", FOLDER) == 0


# --- what changed, not only what is gone ------------------------------------------------------

THEN = int(WHEN.timestamp())
REG, DIR, LINK = stat.S_IFREG | 0o644, stat.S_IFDIR | 0o755, stat.S_IFLNK | 0o777


def on_disk(**spec):
    """A pretend disk: name -> (mode, size, mtime); a name that is not there is gone."""

    def lstat(path):
        found = spec.get(path[len(FOLDER) + 1 :])
        if found is None:
            raise FileNotFoundError(path)
        if isinstance(found, Exception):
            raise found
        mode, size, mtime = found
        return os.stat_result((mode, 0, 0, 1, 0, 0, size, 0, mtime, 0))

    return lstat


def changed(tree, **spec):
    return names(top_level_changed(tree, FOLDER, on_disk(**spec)))


def test_a_file_the_same_as_the_snapshot_is_not_changed():
    assert changed([file("a.png", 5)], **{"a.png": (REG, 5, THEN)}) == []


def test_a_file_with_another_size_is_changed():
    assert changed([file("a.png", 5)], **{"a.png": (REG, 9, THEN)}) == ["a.png"]


def test_a_file_saved_since_is_changed_even_with_the_same_size():
    assert changed([file("a.png", 5)], **{"a.png": (REG, 5, THEN + 60)}) == ["a.png"]


def test_fractions_of_a_second_do_not_count_as_a_change():
    assert changed([file("a.png", 5)], **{"a.png": (REG, 5, THEN + 0.9)}) == []


def test_a_file_that_is_a_folder_today_is_changed():
    assert changed([file("notes", 5)], notes=(DIR, 0, THEN)) == ["notes"]


def test_a_link_is_never_judged_because_its_size_is_not_what_borg_lists():
    assert changed([file("shortcut", 0)], shortcut=(LINK, 24, THEN + 999)) == []


def test_what_cannot_be_read_is_not_judged():
    assert changed([file("secret", 5)], secret=PermissionError("no")) == []


def test_deleted_and_modified_come_together_in_name_order():
    tree = [file("b.png", 5), file("a.png", 5), file("c.png", 5)]
    on = {"b.png": (REG, 5, THEN), "c.png": (REG, 6, THEN)}  # a.png is gone, b is the same, c grew
    assert changed(tree, **on) == ["a.png", "c.png"]


def test_a_deleted_folder_is_one_item_and_its_files_are_not_repeated():
    tree = [folder("trip"), file("trip/1.jpg", 5), file("trip/2.jpg", 5), file("keep.txt", 1)]
    assert changed(tree, **{"keep.txt": (REG, 1, THEN)}) == ["trip"]


def test_a_changed_file_deep_in_a_folder_that_is_still_there_is_found():
    tree = [folder("trip"), folder("trip/raw"), file("trip/raw/2.nef", 100), file("trip/1.jpg", 5)]
    on = {"trip": (DIR, 0, THEN), "trip/raw": (DIR, 0, THEN), "trip/raw/2.nef": (REG, 101, THEN),
          "trip/1.jpg": (REG, 5, THEN)}
    assert changed(tree, **on) == ["trip/raw/2.nef"]


def test_folders_that_are_still_there_are_never_reported_as_changed_themselves():
    tree = [folder("trip"), file("trip/1.jpg", 5)]
    on = {"trip": (DIR, 0, THEN + 500), "trip/1.jpg": (REG, 5, THEN)}  # the folder's own time moved
    assert changed(tree, **on) == []


def test_the_service_finds_changes_with_the_snapshots_name():
    deleted, engine, _ = service([file("a.png", 5)], lstat=on_disk(**{"a.png": (REG, 6, THEN)}))
    assert names(deleted.find_changed("id1", FOLDER)) == ["a.png"]
    assert engine.asked == [("first", FOLDER)]


def test_changes_are_refused_for_an_unknown_snapshot_or_outside_home():
    with pytest.raises(SnapshotNotFound):
        service([])[0].find_changed("nope", FOLDER)
    with pytest.raises(InvalidPath):
        service([])[0].find_changed("first", "/etc")


def test_without_a_repository_nothing_changed():
    assert service([file("a.png")], repo=None)[0].find_changed("first", FOLDER) == []


def test_a_very_long_list_of_changes_is_cut_to_the_limit_in_name_order():
    tree = [file(f"f{n:05d}.txt") for n in range(CHANGE_LIMIT + 50)]  # all gone

    found = service(tree)[0].find_changed("first", FOLDER)

    assert len(found) == CHANGE_LIMIT
    assert names(found)[0] == "f00000.txt" and names(found)[-1] == f"f{CHANGE_LIMIT - 1:05d}.txt"


def test_the_limit_the_window_assumes_is_the_one_the_daemon_applies():
    from delta.ui.folder_listing import SEARCH_CAP

    assert SEARCH_CAP == CHANGE_LIMIT
