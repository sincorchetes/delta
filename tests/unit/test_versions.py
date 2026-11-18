import json
import threading
import time
from datetime import datetime

import pytest

from delta.application.version_service import PARALLEL_LISTINGS, VersionService
from delta.domain.errors import EngineError, InvalidPath
from delta.domain.file_version import FileEntry, FileVersion, distinct_versions
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot
from delta.infrastructure.borg_parsing import parse_file_entry

HOME = "/home/u"


def _snap(n):
    return Snapshot(f"id{n}", f"s{n}", datetime(2026, 1, n))


def _entry(size, day=1):
    return FileEntry(size, datetime(2026, 1, day))


def test_distinct_versions_collapses_runs_and_returns_newest_first():
    same, other = _entry(1), _entry(2)
    versions = [FileVersion(_snap(1), same), FileVersion(_snap(2), same), FileVersion(_snap(3), other)]
    result = distinct_versions(versions)
    assert [v.snapshot.name for v in result] == ["s3", "s1"]


def test_distinct_versions_keeps_a_return_to_older_content():
    a, b = _entry(1), _entry(2)
    versions = [FileVersion(_snap(i), e) for i, e in enumerate([a, b, a], start=1)]
    assert [v.snapshot.name for v in distinct_versions(versions)] == ["s3", "s2", "s1"]


class FakeEngine:
    def __init__(self, entries):
        self.entries = entries

    def list_snapshots(self, repo):
        return [_snap(n) for n in (3, 1, 2)]

    def file_entry(self, repo, snapshot, path):
        return self.entries.get(snapshot)


def test_service_skips_snapshots_without_the_path():
    engine = FakeEngine({"s2": _entry(5), "s3": _entry(6)})
    versions = VersionService(engine, Repository("/r"), HOME).list_versions("/home/u/a")
    assert [v.snapshot.name for v in versions] == ["s3", "s2"]


def test_service_rejects_paths_outside_home():
    with pytest.raises(InvalidPath):
        VersionService(FakeEngine({}), Repository("/r"), HOME).list_versions("/etc/passwd")


def test_service_without_repository_is_empty():
    assert VersionService(FakeEngine({}), None, HOME).list_versions("/home/u/a") == []


def test_parse_file_entry_matches_exact_path_only():
    out = "\n".join(
        json.dumps(d)
        for d in [
            {"path": "home/u/dir", "size": 0, "mtime": "2026-01-01T00:00:00.000000"},
            {"path": "home/u/dir/f", "size": 7, "mtime": "2026-01-02T00:00:00.000000"},
        ]
    )
    assert parse_file_entry(out, "/home/u/dir/f") == FileEntry(7, datetime(2026, 1, 2))
    assert parse_file_entry(out, "/home/u/missing") is None
    assert parse_file_entry("", "/home/u/f") is None


def _folder_listing(*rows):
    return "\n".join(
        json.dumps({"path": p, "type": t, "size": s, "mtime": m}) for p, t, s, m in rows
    )


def test_a_folder_is_fingerprinted_by_everything_below_it():
    out = _folder_listing(
        ("home/u/dir", "d", 0, "2026-01-01T00:00:00.000000"),
        ("home/u/dir/a", "-", 5, "2026-01-03T00:00:00.000000"),
        ("home/u/dir/sub", "d", 0, "2026-01-01T00:00:00.000000"),
        ("home/u/dir/sub/b", "-", 7, "2026-01-02T00:00:00.000000"),
        ("home/u/dir2/other", "-", 99, "2026-02-01T00:00:00.000000"),  # a sibling, not inside
    )
    assert parse_file_entry(out, "/home/u/dir") == FileEntry(12, datetime(2026, 1, 3), is_dir=True)


def test_an_empty_folder_keeps_its_own_mtime():
    out = _folder_listing(("home/u/dir", "d", 0, "2026-01-01T00:00:00.000000"))
    assert parse_file_entry(out, "/home/u/dir") == FileEntry(0, datetime(2026, 1, 1), is_dir=True)


def test_a_deleted_file_changes_the_folder_fingerprint():
    with_b = _folder_listing(
        ("home/u/dir", "d", 0, "2026-01-01T00:00:00.000000"),
        ("home/u/dir/a", "-", 5, "2026-01-03T00:00:00.000000"),
        ("home/u/dir/b", "-", 7, "2026-01-02T00:00:00.000000"),
    )
    without_b = _folder_listing(
        ("home/u/dir", "d", 0, "2026-01-01T00:00:00.000000"),
        ("home/u/dir/a", "-", 5, "2026-01-03T00:00:00.000000"),
    )
    assert parse_file_entry(with_b, "/home/u/dir") != parse_file_entry(without_b, "/home/u/dir")


def test_parse_file_entry_rejects_malformed_output():
    with pytest.raises(EngineError):
        parse_file_entry("not json", "/home/u/f")


# --- asking about every snapshot at once -------------------------------------------------------


class SlowEngine:
    """Each question takes a moment and the test sees how many are open at the same time."""

    def __init__(self, entries, delay=0.05):
        self.entries, self.delay = entries, delay
        self.open = self.most_open = 0
        self._lock = threading.Lock()

    def list_snapshots(self, repo):
        return [_snap(n) for n in (3, 1, 2, 5, 4)]

    def file_entry(self, repo, snapshot, path):
        with self._lock:
            self.open += 1
            self.most_open = max(self.most_open, self.open)
        time.sleep(self.delay)
        with self._lock:
            self.open -= 1
        return self.entries.get(snapshot)


def test_every_snapshot_is_asked_about_and_the_questions_overlap():
    engine = SlowEngine({f"s{n}": _entry(n) for n in range(1, 6)})

    versions = VersionService(engine, Repository("/r"), HOME).list_versions("/home/u/a")

    assert len(versions) == 5
    assert 1 < engine.most_open <= PARALLEL_LISTINGS


def test_the_results_keep_the_order_of_the_snapshots_not_the_order_they_finish_in():
    class Reversed(SlowEngine):
        def file_entry(self, repo, snapshot, path):
            time.sleep(0.2 - int(snapshot[1:]) * 0.03)  # the oldest takes the longest
            return self.entries.get(snapshot)

    engine = Reversed({f"s{n}": _entry(n, day=n) for n in range(1, 6)})

    versions = VersionService(engine, Repository("/r"), HOME).list_versions("/home/u/a")

    assert [v.snapshot.name for v in versions] == ["s5", "s4", "s3", "s2", "s1"]  # newest first


def test_snapshots_without_the_path_are_skipped_whatever_the_order():
    engine = SlowEngine({"s2": _entry(2), "s4": _entry(4)})
    versions = VersionService(engine, Repository("/r"), HOME).list_versions("/home/u/a")
    assert [v.snapshot.name for v in versions] == ["s4", "s2"]


def test_a_failing_question_fails_the_whole_listing_as_before():
    class Failing(SlowEngine):
        def file_entry(self, repo, snapshot, path):
            if snapshot == "s3":
                raise EngineError("repository is locked")
            return super().file_entry(repo, snapshot, path)

    with pytest.raises(EngineError):
        VersionService(Failing({}), Repository("/r"), HOME).list_versions("/home/u/a")


def test_it_never_runs_more_borg_processes_at_once_than_allowed():
    engine = SlowEngine({}, delay=0.1)
    VersionService(engine, Repository("/r"), HOME).list_versions("/home/u/a")
    assert engine.most_open <= PARALLEL_LISTINGS
