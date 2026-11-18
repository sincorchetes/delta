import shutil

import pytest
from conftest import call_and_wait_finished

from delta.application.backup_service import BackupService
from delta.application.restore_service import RestoreService
from delta.application.snapshot_service import SnapshotService
from delta.daemon.job_runner import JobRunner
from delta.daemon.service import DeltaService
from delta.domain.backup_job import BackupJob
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


@pytest.fixture
def world(bus, tmp_path):
    home = tmp_path / "home"
    data = home / "docs"
    data.mkdir(parents=True)
    (data / "a.txt").write_text("v1")
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "bh")})
    repo = Repository(str(tmp_path / "repo"))
    runner.init(repo)
    runner.create(repo, BackupJob("j", (str(home),)), "first")
    (data / "a.txt").write_text("v2")
    target = home / "restored"
    target.mkdir()
    service = DeltaService(
        bus,
        SnapshotService(runner, repo),
        JobRunner(bus),
        BackupService(runner, repo, (str(home),)),
        RestoreService(runner, repo, str(home)),
    )
    yield home, data, target
    service.unregister()


def _restore(bus, snapshot, source, target):
    return call_and_wait_finished(bus, "Restore", GLib.Variant("(sss)", (snapshot, source, target)))


def test_restore_extracts_old_version_under_target(bus, world):
    home, data, target = world

    job_id, finished, error = _restore(bus, "first", str(data / "a.txt"), str(target))

    assert error is None and finished is not None
    assert finished[0] == job_id
    assert finished[1] is True, finished[2]
    restored = target / str(data / "a.txt").lstrip("/")
    assert restored.read_text() == "v1"
    assert (data / "a.txt").read_text() == "v2"


def test_restore_rejects_target_outside_home(bus, world, tmp_path):
    home, data, _ = world
    outside = tmp_path / "outside"
    outside.mkdir()

    _, finished, error = _restore(bus, "first", str(data / "a.txt"), str(outside))

    assert finished is None
    assert "InvalidPath" in error


def test_restore_rejects_dotdot(bus, world):
    home, data, target = world

    _, finished, error = _restore(bus, "first", f"{data}/../../etc/passwd", str(target))

    assert finished is None and "InvalidPath" in error


def test_restore_rejects_symlink_escaping_home(bus, world, tmp_path):
    home, data, _ = world
    outside = tmp_path / "outside"
    outside.mkdir()
    link = home / "link"
    link.symlink_to(outside)

    _, finished, error = _restore(bus, "first", str(data / "a.txt"), str(link))

    assert finished is None and "InvalidPath" in error


def test_restore_unknown_snapshot_fails_job(bus, world):
    home, data, target = world

    _, finished, _ = _restore(bus, "nope", str(data / "a.txt"), str(target))

    assert finished is not None and finished[1] is False
