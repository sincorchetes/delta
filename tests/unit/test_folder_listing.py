import json
from datetime import datetime

import pytest

from delta.application.version_service import SEARCH_LIMIT, VersionService
from delta.domain.errors import EngineError, InvalidPath, SnapshotNotFound
from delta.domain.file_version import FolderEntry
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot
from delta.infrastructure.borg_parsing import parse_folder_listing, parse_folder_search

HOME = "/home/u"


def listing(*rows):
    return "\n".join(
        json.dumps({"path": p, "type": t, "size": s, "mtime": m}) for p, t, s, m in rows
    )


def by_name(entries):
    return {entry.name: entry for entry in entries}


def test_only_the_direct_children_are_listed():
    out = listing(
        ("home/u/dir", "d", 0, "2026-01-01T00:00:00.000000"),
        ("home/u/dir/a.txt", "-", 5, "2026-01-02T00:00:00.000000"),
        ("home/u/dir/sub", "d", 0, "2026-01-03T00:00:00.000000"),
        ("home/u/dir/sub/deep.txt", "-", 7, "2026-01-04T00:00:00.000000"),
    )

    entries = by_name(parse_folder_listing(out, "/home/u/dir"))

    assert set(entries) == {"a.txt", "sub"}
    assert entries["a.txt"] == FolderEntry("a.txt", False, 5, datetime(2026, 1, 2))


def test_a_subfolder_is_sized_and_dated_by_what_it_holds():
    out = listing(
        ("home/u/dir/sub", "d", 0, "2026-01-03T00:00:00.000000"),
        ("home/u/dir/sub/one", "-", 7, "2026-01-05T00:00:00.000000"),
        ("home/u/dir/sub/two", "-", 3, "2026-01-04T00:00:00.000000"),
    )

    sub = by_name(parse_folder_listing(out, "/home/u/dir"))["sub"]

    assert sub.is_dir and sub.size == 10 and sub.mtime == datetime(2026, 1, 5)


def test_a_folder_with_no_line_of_its_own_is_still_a_folder():
    out = listing(("home/u/dir/ghost/inside.txt", "-", 4, "2026-01-02T00:00:00.000000"))
    assert by_name(parse_folder_listing(out, "/home/u/dir"))["ghost"].is_dir


def test_an_empty_folder_is_a_folder_of_size_zero():
    out = listing(("home/u/dir/empty", "d", 0, "2026-01-02T00:00:00.000000"))
    assert parse_folder_listing(out, "/home/u/dir") == [
        FolderEntry("empty", True, 0, datetime(2026, 1, 2))
    ]


def test_a_symlink_is_listed_as_a_file():
    out = listing(("home/u/dir/link", "l", 0, "2026-01-02T00:00:00.000000"))
    assert parse_folder_listing(out, "/home/u/dir")[0].is_dir is False


def test_a_sibling_with_a_longer_name_is_not_inside():
    out = listing(("home/u/dir2/other", "-", 1, "2026-01-02T00:00:00.000000"))
    assert parse_folder_listing(out, "/home/u/dir") == []


def test_the_folder_itself_and_empty_output_give_nothing():
    own = listing(("home/u/dir", "d", 0, "2026-01-01T00:00:00.000000"))
    assert parse_folder_listing(own, "/home/u/dir") == []
    assert parse_folder_listing("", "/home/u/dir") == []


def test_malformed_output_is_an_engine_error():
    with pytest.raises(EngineError):
        parse_folder_listing("not json", "/home/u/dir")


class FakeEngine:
    def __init__(self):
        self.asked = []

    def list_snapshots(self, repo):
        return [Snapshot("id1", "first", datetime(2026, 1, 1))]

    def list_folder(self, repo, snapshot, path):
        self.asked.append((snapshot, path))
        return [FolderEntry("a", False, 1, datetime(2026, 1, 1))]

    def search_folder(self, repo, snapshot, path, query, limit):
        self.searched = (snapshot, path, query, limit)
        return [FolderEntry("sub/hit.txt", False, 1, datetime(2026, 1, 1))]


def service(engine, repo=Repository("/r")):
    return VersionService(engine, repo, HOME)


def test_a_snapshot_can_be_named_by_id_or_name_and_the_engine_gets_its_name():
    engine = FakeEngine()
    service(engine).list_folder("id1", "/home/u/dir")
    service(engine).list_folder("first", "/home/u/dir")
    assert engine.asked == [("first", "/home/u/dir")] * 2


def test_an_unknown_snapshot_is_refused():
    with pytest.raises(SnapshotNotFound):
        service(FakeEngine()).list_folder("nope", "/home/u/dir")


def test_only_folders_inside_home_can_be_listed():
    for outside in ("/etc", "/home/u/../x", "relative"):
        with pytest.raises(InvalidPath):
            service(FakeEngine()).list_folder("first", outside)


def test_without_a_repository_the_folder_is_empty():
    assert service(FakeEngine(), repo=None).list_folder("first", "/home/u/dir") == []


# --- searching below a folder ------------------------------------------------------------------

TREE = listing(
    ("home/u/dir", "d", 0, "2026-01-01T00:00:00.000000"),
    ("home/u/dir/Trip.PNG", "-", 5, "2026-01-02T00:00:00.000000"),
    ("home/u/dir/notes.txt", "-", 6, "2026-01-02T00:00:00.000000"),
    ("home/u/dir/photos", "d", 0, "2026-01-03T00:00:00.000000"),
    ("home/u/dir/photos/2026", "d", 0, "2026-01-03T00:00:00.000000"),
    ("home/u/dir/photos/2026/trip-day2.jpg", "-", 7, "2026-01-04T00:00:00.000000"),
    ("home/u/dir2/trip.png", "-", 9, "2026-01-05T00:00:00.000000"),  # a sibling folder
)


def found(query, limit=100):
    return [e.name for e in parse_folder_search(TREE, "/home/u/dir", query, limit)]


def test_a_search_finds_matches_at_any_depth_with_paths_relative_to_the_folder():
    assert found("trip") == ["Trip.PNG", "photos/2026/trip-day2.jpg"]


def test_a_search_matches_the_name_not_the_folders_on_the_way():
    assert found("2026") == ["photos/2026"]  # the folder itself, not what is inside it


def test_a_search_ignores_case_and_surrounding_spaces():
    assert found("  PNG ") == ["Trip.PNG"]


def test_a_search_never_leaves_the_folder():
    assert "trip.png" not in found("trip")


def test_a_hit_knows_whether_it_is_a_folder_and_when_it_was_saved():
    hit = {e.name: e for e in parse_folder_search(TREE, "/home/u/dir", "photos", 10)}["photos"]
    assert hit.is_dir and hit.mtime == datetime(2026, 1, 3)


def test_a_search_stops_at_the_limit():
    assert found("t", limit=2) == ["Trip.PNG", "notes.txt"]


def test_malformed_output_stops_a_search_too():
    with pytest.raises(EngineError):
        parse_folder_search("not json", "/home/u/dir", "x", 10)


def test_the_service_searches_with_the_snapshot_name_and_the_cap():
    engine = FakeEngine()
    hits = service(engine).search_folder("id1", "/home/u/dir", "hit")
    assert [h.name for h in hits] == ["sub/hit.txt"]
    assert engine.searched == ("first", "/home/u/dir", "hit", SEARCH_LIMIT)


def test_a_blank_search_returns_nothing_without_asking_borg():
    engine = FakeEngine()
    assert service(engine).search_folder("first", "/home/u/dir", "   ") == []
    assert not hasattr(engine, "searched")


def test_a_search_in_an_unknown_snapshot_is_refused():
    with pytest.raises(SnapshotNotFound):
        service(FakeEngine()).search_folder("nope", "/home/u/dir", "x")


def test_only_folders_inside_home_can_be_searched():
    with pytest.raises(InvalidPath):
        service(FakeEngine()).search_folder("first", "/etc", "x")


def test_without_a_repository_a_search_is_empty():
    assert service(FakeEngine(), repo=None).search_folder("first", "/home/u/dir", "x") == []
