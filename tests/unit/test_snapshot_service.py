from datetime import datetime

from delta.application.snapshot_service import SnapshotService
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot


class FakeEngine:
    def list_snapshots(self, repo):
        return [
            Snapshot("1", "old", datetime(2026, 1, 1)),
            Snapshot("2", "new", datetime(2026, 6, 1)),
        ]


def test_lists_newest_first():
    service = SnapshotService(FakeEngine(), Repository("/r"))
    assert [s.name for s in service.list_snapshots()] == ["new", "old"]


def test_empty_without_repository():
    assert SnapshotService(FakeEngine(), None).list_snapshots() == []


def test_the_latest_backup_is_the_newest_snapshot_or_zero():
    from datetime import datetime, timezone

    from delta.application.snapshot_service import SnapshotService, newest_timestamp
    from delta.domain.repository import Repository
    from delta.domain.snapshot import Snapshot

    old = Snapshot("a", "a", datetime(2026, 1, 1, tzinfo=timezone.utc))
    new = Snapshot("b", "b", datetime(2026, 5, 1, tzinfo=timezone.utc))

    class Engine:
        def list_snapshots(self, repo):
            return [old, new]

    assert newest_timestamp([old, new]) == int(new.created.timestamp())
    assert newest_timestamp([]) == 0
    assert SnapshotService(Engine(), Repository("/r")).latest_backup() == int(new.created.timestamp())
    assert SnapshotService(Engine(), None).latest_backup() == 0
