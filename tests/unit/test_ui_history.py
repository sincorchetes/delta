from datetime import datetime

from delta.ui.history import build_history, describe_count

NOW = datetime(2026, 11, 10, 18, 0, 0)


def epoch(hour, minute=0, day=10):
    return int(datetime(2026, 11, day, hour, minute).timestamp())


def rows(*times):
    return [{"id": f"id{n}", "name": f"snap-{n}", "time": t} for n, t in enumerate(times)]


def test_the_newest_backup_comes_first_whatever_the_order_received():
    history = build_history(rows(epoch(9), epoch(17), epoch(12)), NOW)
    assert [row.name for row in history] == ["snap-1", "snap-2", "snap-0"]


def test_the_date_is_unambiguous_and_the_age_is_friendly():
    (row,) = build_history(rows(epoch(17, 30)), NOW)
    assert row.when == "2026-11-10  17:30"
    assert row.ago == "30 minutes ago"


def test_an_old_backup_is_described_in_days():
    (row,) = build_history(rows(epoch(12, day=7)), NOW)
    assert row.ago == "3 days ago"


def test_no_backups_gives_an_empty_table():
    assert build_history([], NOW) == []


def test_the_count_is_pluralised():
    assert describe_count(1) == "1 backup"
    assert describe_count(2) == "2 backups"
