import pytest

from delta.application.restore_service import RestoreService
from delta.domain.errors import DeltaError, InvalidPath, SnapshotNotFound
from delta.domain.paths import validate_restore
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot
from datetime import datetime

HOME = "/home/u"


def test_valid_paths_are_normalized():
    assert validate_restore("/home/u/a//b/", "/home/u/./t", HOME) == ("/home/u/a/b", "/home/u/t")


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("rel/a", "/home/u/t"),
        ("/home/u/a", "t"),
        ("/home/u/../etc/passwd", "/home/u/t"),
        ("/home/u/a", "/home/u/../../tmp"),
        ("/etc/passwd", "/home/u/t"),
        ("/home/u/a", "/tmp/x"),
        ("/home/user2/a", "/home/u/t"),
    ],
)
def test_invalid_paths_are_rejected(source, target):
    with pytest.raises(InvalidPath):
        validate_restore(source, target, HOME)


class FakeEngine:
    def __init__(self):
        self.extracted = []

    def list_snapshots(self, repo):
        return [Snapshot("id1", "name1", datetime(2026, 1, 1))]

    def extract(self, repo, snapshot, paths, destination):
        self.extracted.append((snapshot, paths, destination))


def test_prepare_rejects_resolved_escape():
    service = RestoreService(FakeEngine(), Repository("/r"), HOME, resolve=lambda p: p if p == HOME else "/tmp/elsewhere")
    with pytest.raises(InvalidPath):
        service.prepare("/home/u/a", "/home/u/link")


def test_restore_resolves_snapshot_by_id_or_name(tmp_path):
    engine = FakeEngine()
    service = RestoreService(engine, Repository("/r"), HOME)
    service.restore("id1", "/home/u/a", str(tmp_path))
    service.restore("name1", "/home/u/a", str(tmp_path))
    assert [e[0] for e in engine.extracted] == ["name1", "name1"]


def test_restore_unknown_snapshot(tmp_path):
    service = RestoreService(FakeEngine(), Repository("/r"), HOME)
    with pytest.raises(SnapshotNotFound):
        service.restore("zzz", "/home/u/a", str(tmp_path))


def test_restore_requires_repository_and_existing_target(tmp_path):
    with pytest.raises(DeltaError):
        RestoreService(FakeEngine(), None, HOME).restore("id1", "/home/u/a", str(tmp_path))
    with pytest.raises(InvalidPath):
        RestoreService(FakeEngine(), Repository("/r"), HOME).restore("id1", "/home/u/a", str(tmp_path / "x"))
