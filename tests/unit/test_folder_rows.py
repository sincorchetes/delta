import stat as stat_module
from datetime import datetime

import pytest

from delta.ui.folder_listing import (
    Change,
    FolderRow,
    Show,
    apply_filter,
    build_folder_rows,
    change_label,
    empty_message,
    classify,
    inside_names,
    inside_root,
    join_path,
    row_titles,
)

MTIME = int(datetime(2026, 11, 3, 14, 10).timestamp())


def row(name, is_dir=False, size=1500):
    return {"name": name, "is_dir": is_dir, "size": size, "mtime": MTIME}


def test_folders_come_first_then_everything_by_name_ignoring_case():
    rows = build_folder_rows([row("b.txt"), row("Zeta", is_dir=True), row("A.txt"), row("alpha", is_dir=True)])
    assert [r.name for r in rows] == ["alpha", "Zeta", "A.txt", "b.txt"]


def test_a_row_says_its_size_and_when_it_was_saved():
    (one,) = build_folder_rows([row("a.txt", size=2_400_000)])
    assert one.detail == "2.4 MB · 2026-11-03  14:10"
    assert one.size == 2_400_000 and one.is_dir is False


def test_a_folder_row_keeps_its_flag():
    (one,) = build_folder_rows([row("sub", is_dir=True, size=10)])
    assert one.is_dir is True


def test_no_rows_is_an_empty_list():
    assert build_folder_rows([]) == []


def test_a_child_path_never_doubles_the_slash():
    assert join_path("/home/u/dir", "a b.txt") == "/home/u/dir/a b.txt"
    assert join_path("/home/u/dir/", "a") == "/home/u/dir/a"


def test_navigation_stays_inside_the_opened_folder():
    assert inside_root("/home/u/dir", "/home/u/dir")
    assert inside_root("/home/u/dir/sub/deep", "/home/u/dir")
    assert not inside_root("/home/u", "/home/u/dir")
    assert not inside_root("/home/u/dir2", "/home/u/dir")


# --- comparing the backup with what is on disk today -------------------------------------------

FILE_MODE, DIR_MODE = stat_module.S_IFREG | 0o644, stat_module.S_IFDIR | 0o755


class Stat:
    def __init__(self, mode=FILE_MODE, size=1500, mtime=MTIME):
        self.st_mode, self.st_size, self.st_mtime = mode, size, mtime


def disk(**entries):
    """A pretend disk under /home/u/d: unknown names are gone; a value of an exception is raised."""

    def lstat(path):
        found = entries.get(path.rsplit("/", 1)[-1].replace(" ", "_").replace(".", "_"))
        if found is None:
            raise FileNotFoundError(path)
        if isinstance(found, Exception):
            raise found
        return found

    return lstat


def rows_of(*rows, **entries):
    return build_folder_rows(list(rows), base="/home/u/d", lstat=disk(**entries))


def only(rows):
    (one,) = rows
    return one


def test_a_file_that_is_gone_is_deleted():
    assert only(rows_of(row("a.txt"))).change is Change.DELETED


def test_a_file_with_the_same_size_and_time_is_unchanged():
    assert only(rows_of(row("a.txt"), a_txt=Stat())).change is Change.UNCHANGED


@pytest.mark.parametrize(
    "now",
    [Stat(size=9), Stat(mtime=MTIME + 60), Stat(mode=DIR_MODE)],
    ids=["other size", "saved since", "a folder now"],
)
def test_a_file_that_differs_today_is_modified(now):
    assert only(rows_of(row("a.txt"), a_txt=now)).change is Change.MODIFIED


def test_a_folder_that_is_still_there_is_not_judged():
    assert only(rows_of(row("sub", is_dir=True), sub=Stat(mode=DIR_MODE))).change is Change.UNKNOWN


def test_a_folder_that_is_gone_is_deleted_and_one_that_became_a_file_is_modified():
    assert only(rows_of(row("sub", is_dir=True))).change is Change.DELETED
    assert only(rows_of(row("sub", is_dir=True), sub=Stat(mode=FILE_MODE))).change is Change.MODIFIED


def test_a_disk_that_cannot_be_asked_says_nothing_rather_than_deleted():
    assert only(rows_of(row("a.txt"), a_txt=PermissionError("no"))).change is Change.UNKNOWN


def test_a_path_under_a_file_is_deleted_not_an_error():
    assert only(rows_of(row("a.txt"), a_txt=NotADirectoryError("x"))).change is Change.DELETED


def test_without_a_base_folder_nothing_is_compared():
    assert only(build_folder_rows([row("a.txt")])).change is Change.UNKNOWN


def test_the_mtime_is_kept_on_the_row():
    assert only(build_folder_rows([row("a.txt")])).mtime == MTIME


def test_a_search_hit_that_is_a_folder_shows_no_size():
    hit = only(build_folder_rows([row("a/b", is_dir=True, size=0)], dir_sizes=False))
    assert hit.detail == "2026-11-03  14:10"


def test_classify_is_the_same_decision_without_any_disk():
    assert classify(False, 5, 100, None) is Change.DELETED
    assert classify(False, 5, 100, Stat(size=5, mtime=100.9)) is Change.UNCHANGED  # seconds, not fractions


@pytest.mark.parametrize(
    ("change", "label"),
    [
        (Change.DELETED, "Deleted"),
        (Change.MODIFIED, "Modified"),
        (Change.UNCHANGED, "Unchanged"),
        (Change.UNKNOWN, ""),
    ],
)
def test_each_change_has_a_small_label(change, label):
    assert change_label(change) == label


def test_a_listed_row_is_titled_by_its_name_and_dated():
    assert row_titles(only(build_folder_rows([row("a.txt")]))) == ("a.txt", "1.5 kB · 2026-11-03  14:10")


def test_a_search_hit_is_titled_by_its_own_name_with_the_folder_it_is_in():
    hit = only(build_folder_rows([row("photos/2026/trip.png")]))
    assert row_titles(hit) == ("trip.png", "photos/2026  ·  1.5 kB · 2026-11-03  14:10")


# --- filtering and searching -------------------------------------------------------------------


def named(*specs):
    """(name, is_dir, change) -> FolderRow"""
    return [FolderRow(name, is_dir, 1, MTIME, "", change) for name, is_dir, change in specs]


MIX = named(
    ("gone.txt", False, Change.DELETED),
    ("edited.txt", False, Change.MODIFIED),
    ("same.txt", False, Change.UNCHANGED),
    ("sub", True, Change.UNKNOWN),
    ("gone-dir", True, Change.DELETED),
)


def names(rows):
    return [r.name for r in rows]


def test_all_shows_everything():
    assert names(apply_filter(MIX, "", Show.ALL)) == names(MIX)


def test_deleted_keeps_the_deleted_and_the_folders_that_lead_to_more():
    assert names(apply_filter(MIX, "", Show.DELETED)) == ["gone.txt", "sub", "gone-dir"]


def test_changed_adds_the_modified():
    assert names(apply_filter(MIX, "", Show.CHANGED)) == ["gone.txt", "edited.txt", "sub", "gone-dir"]


def test_the_name_filter_ignores_case_and_surrounding_space():
    assert names(apply_filter(MIX, "  GONE ", Show.ALL)) == ["gone.txt", "gone-dir"]


def test_the_name_and_the_change_filters_combine():
    assert names(apply_filter(MIX, "txt", Show.DELETED)) == ["gone.txt"]


def test_a_search_matches_inside_a_relative_path():
    rows = named(("Photos/2026/trip.png", False, Change.DELETED), ("notes.txt", False, Change.UNCHANGED))
    assert names(apply_filter(rows, "trip", Show.ALL)) == ["Photos/2026/trip.png"]


def test_an_empty_listing_says_why_it_is_empty():
    assert empty_message(True, False)[0] == "Nothing found"
    assert empty_message(False, True)[0] == "Nothing to show"
    assert empty_message(False, False)[0] == "This folder was empty"
    assert empty_message(True, True)[0] == "Nothing found"  # a search is the more specific reason


def test_a_link_is_not_judged_because_its_size_is_not_what_borg_lists():
    link = Stat(mode=stat_module.S_IFLNK | 0o777, size=24, mtime=MTIME + 999)
    assert only(rows_of(row("shortcut", size=0), shortcut=link)).change is Change.UNKNOWN


# --- folders with something changed inside -----------------------------------------------------


def test_the_folders_with_changes_below_are_named_from_the_changes_anywhere_below():
    changes = [{"name": "trip/raw/2.nef"}, {"name": "trip/1.jpg"}, {"name": "docs/a.txt"}, {"name": "top-level.txt"}]
    assert inside_names(changes) == {"trip", "docs"}  # a change right here is not "inside" any folder


def test_there_is_nothing_inside_when_nothing_changed():
    assert inside_names([]) == set()


def test_a_folder_that_is_still_there_with_changes_below_says_so():
    rows = build_folder_rows(
        [row("trip", is_dir=True)], base="/home/u/d", lstat=disk(trip=Stat(mode=DIR_MODE)), inside={"trip"}
    )
    assert only(rows).change is Change.INSIDE


def test_a_folder_without_changes_below_says_nothing():
    rows = build_folder_rows(
        [row("trip", is_dir=True)], base="/home/u/d", lstat=disk(trip=Stat(mode=DIR_MODE)), inside={"other"}
    )
    assert only(rows).change is Change.UNKNOWN


def test_a_deleted_folder_is_deleted_not_merely_changed_inside():
    rows = build_folder_rows([row("trip", is_dir=True)], base="/home/u/d", lstat=disk(), inside={"trip"})
    assert only(rows).change is Change.DELETED


def test_a_file_never_says_changed_inside():
    rows = build_folder_rows([row("a.txt")], base="/home/u/d", lstat=disk(a_txt=Stat()), inside={"a.txt"})
    assert only(rows).change is Change.UNCHANGED


def test_the_changed_filter_keeps_the_folders_that_changed_inside():
    mixed = named(("trip", True, Change.INSIDE), ("quiet", True, Change.UNKNOWN), ("same.txt", False, Change.UNCHANGED))
    assert names(apply_filter(mixed, "", Show.CHANGED)) == ["trip", "quiet"]


def test_changed_inside_has_a_label_and_a_style():
    from delta.ui.folder_listing import change_label

    assert change_label(Change.INSIDE) == "Changed inside"
