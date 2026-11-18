from datetime import datetime

import pytest

from delta.ui.versions import build_versions, format_size, step_index

NOW = datetime(2026, 11, 10, 18, 0, 0)


def epoch(day, hour, minute=0):
    return int(datetime(2026, 11, day, hour, minute).timestamp())


def row(name, mtime, time, size=1500):
    return {"id": f"id-{name}", "name": name, "time": time, "mtime": mtime, "size": size}


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (0, "0 bytes"),
        (999, "999 bytes"),
        (1000, "1.0 kB"),
        (1500, "1.5 kB"),
        (2_400_000, "2.4 MB"),
        (3_000_000_000, "3.0 GB"),
        (5_000_000_000_000, "5.0 TB"),
        (7_000_000_000_000_000, "7000.0 TB"),
    ],
)
def test_sizes_use_decimal_units(size, expected):
    assert format_size(size) == expected


def test_the_latest_saved_version_comes_first():
    rows = [row("a", epoch(3, 9), epoch(3, 10)), row("c", epoch(9, 9), epoch(9, 10)), row("b", epoch(5, 9), epoch(5, 10))]
    assert [v.snapshot for v in build_versions(rows, NOW)] == ["c", "b", "a"]


def test_a_version_is_recognised_by_when_the_file_was_saved():
    (version,) = build_versions([row("snap", epoch(3, 14, 10), epoch(10, 17, 30), size=2_400_000)], NOW)
    assert version.modified == "2026-11-03  14:10"
    assert version.backed_up == "Backed up 30 minutes ago · 2.4 MB"


def test_the_snapshot_to_restore_is_the_one_the_version_came_from():
    (version,) = build_versions([row("2026-11-10T17-33-14-288851", epoch(3, 9), epoch(10, 17))], NOW)
    assert version.snapshot == "2026-11-10T17-33-14-288851"


def test_a_version_knows_its_size_and_whether_it_is_a_folder():
    folder = {**row("snap", epoch(3, 9), epoch(10, 17), size=42), "is_dir": True}
    (version,) = build_versions([folder], NOW)
    assert version.size == 42 and version.is_dir is True
    (plain,) = build_versions([row("snap", epoch(3, 9), epoch(10, 17))], NOW)
    assert plain.is_dir is False  # an older daemon does not send the key


def test_no_versions_gives_an_empty_list():
    assert build_versions([], NOW) == []


@pytest.mark.parametrize(
    ("current", "delta", "count", "expected"),
    [
        (0, 1, 5, 1),  # one older
        (3, -1, 5, 2),  # one newer
        (4, 1, 5, None),  # already the oldest
        (0, -1, 5, None),  # already the newest
        (None, 1, 5, None),  # nothing chosen yet
        (0, 1, 1, None),  # a single version
        (2, 2, 5, 4),
        (2, 3, 5, None),
    ],
)
def test_stepping_through_the_versions_never_runs_off_either_end(current, delta, count, expected):
    assert step_index(current, delta, count) == expected
