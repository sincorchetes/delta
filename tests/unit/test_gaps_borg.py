"""What a mutation run showed nothing watched in the borg command lines and in reading its output."""

import json
from datetime import datetime

from delta.domain.file_version import FileEntry, FolderEntry
from delta.domain.progress import ProgressEvent
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot
from delta.infrastructure import borg_commands as commands
from delta.infrastructure.borg_parsing import (
    parse_file_entry,
    parse_folder_listing,
    parse_folder_search,
    parse_folder_tree,
    parse_progress,
)

REPO = Repository("/srv/repo")
STAMP = "2026-01-02T03:04:05.000000"
WHEN = datetime(2026, 1, 2, 3, 4, 5)


# --- the exact command lines handed to borg ----------------------------------------------------------


def test_borg_is_started_with_exactly_these_arguments():
    assert commands.init(REPO) == ["borg", "init", "--encryption=repokey-blake2", "/srv/repo"]
    assert commands.list_archives(REPO) == ["borg", "list", "--json", "/srv/repo"]
    assert commands.break_lock(REPO) == ["borg", "break-lock", "/srv/repo"]
    assert commands.check(REPO) == ["borg", "check", "--repository-only", "/srv/repo"]


def test_a_path_is_given_to_borg_without_its_leading_slash_and_nothing_else_trimmed():
    assert commands.list_path(REPO, "a", "/home/u/dir/") == [
        "borg", "list", "--json-lines", "/srv/repo::a", "home/u/dir/",
    ]
    assert commands.extract(REPO, "a", ("/home/u/x", "/etc/y/")) == [
        "borg", "extract", "/srv/repo::a", "home/u/x", "etc/y/",
    ]


# --- reading what borg says --------------------------------------------------------------------------


def line(path, kind="-", **fields):
    return json.dumps({"path": path, "type": kind, "mtime": STAMP, **fields})


def test_a_snapshot_keeps_the_id_borg_gave_it():
    listing = json.dumps({"archives": [{"id": "abc", "name": "first", "time": STAMP}]})

    from delta.infrastructure.borg_parsing import parse_snapshots

    assert parse_snapshots(listing) == [Snapshot("abc", "first", WHEN)]


def test_an_entry_without_a_size_weighs_nothing():
    assert parse_file_entry(line("home/u/f"), "/home/u/f") == FileEntry(0, WHEN)
    folder = "\n".join([line("home/u/d", "d"), line("home/u/d/inner")])
    assert parse_file_entry(folder, "/home/u/d") == FileEntry(0, WHEN, is_dir=True)


def test_the_tree_below_a_folder_is_listed_with_relative_names_and_what_borg_said_of_each():
    stdout = "\n".join([
        line("home/u/other/x", size=9),  # not below the folder: skipped, and the rest is still read
        line("home/u/dir", "d"),  # the folder itself
        line("home/u/dir/a.txt", size=5),
        line("home/u/dir/sub", "d"),  # no size at all
    ])

    assert parse_folder_tree(stdout, "/home/u/dir") == [
        FolderEntry("a.txt", False, 5, WHEN),
        FolderEntry("sub", True, 0, WHEN),
    ]


def test_one_level_of_a_folder_sums_what_is_below_each_entry():
    stdout = "\n".join([
        line("home/u/dir//ghost", size=1),
        line("home/u/dir/a.txt", size=5),
        line("home/u/dir/sub", "d"),
        line("home/u/dir/sub/deep.txt", size=7),
        line("home/u/dir/nosize.txt"),
    ])

    assert {e.name: (e.is_dir, e.size) for e in parse_folder_listing(stdout, "/home/u/dir")} == {
        "a.txt": (False, 5), "sub": (True, 7), "nosize.txt": (False, 0),
    }


def test_a_search_reports_each_hit_with_its_size_and_date():
    stdout = "\n".join([
        line("home/u/dir/photos/Holiday.JPG", size=12),
        line("home/u/dir/photos", "d"),
        line("home/u/dir/notes.txt", size=3),
    ])

    assert parse_folder_search(stdout, "/home/u/dir", "jpg", 10) == [FolderEntry("photos/Holiday.JPG", False, 12, WHEN)]
    assert parse_folder_search(stdout, "/home/u/dir", "photos", 10)[0] == FolderEntry("photos", True, 0, WHEN)


def test_progress_lines_missing_fields_count_as_nothing_yet():
    assert parse_progress(json.dumps({"type": "archive_progress"})) == ProgressEvent(0, 0, "")
