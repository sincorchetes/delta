import glob
import shutil

import pytest
from conftest import call_and_wait_finished
from gi.repository import GLib

from delta.application.backup_service import BackupService
from delta.application.restore_service import RestoreService
from delta.application.snapshot_service import SnapshotService
from delta.daemon.job_runner import JobRunner
from delta.daemon.service import DeltaService
from delta.domain.backup_job import BackupJob
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


@pytest.fixture
def world(bus, tmp_path):
    home = tmp_path / "home"
    docs = home / "docs"
    docs.mkdir(parents=True)
    (docs / "a.txt").write_text("v1")
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "bh")})
    repo = Repository(str(tmp_path / "repo"))
    runner.init(repo)
    runner.create(repo, BackupJob("j", (str(home),)), "first")
    (docs / "a.txt").write_text("v2")
    service = DeltaService(
        bus,
        SnapshotService(runner, repo),
        JobRunner(bus),
        BackupService(runner, repo, (str(home),)),
        RestoreService(runner, repo, str(home)),
    )
    yield docs
    service.unregister()


def _call(bus, method, snapshot, path):
    return call_and_wait_finished(bus, method, GLib.Variant("(ss)", (snapshot, path)))


def test_restore_as_copy_leaves_the_current_file_alone(bus, world):
    docs = world

    _, finished, error = _call(bus, "RestoreAsCopy", "first", str(docs / "a.txt"))

    assert error is None and finished is not None and finished[1] is True, finished
    copies = glob.glob(str(docs / "a (restored *).txt"))
    assert len(copies) == 1 and finished[2] == copies[0]
    assert open(copies[0]).read() == "v1"
    assert (docs / "a.txt").read_text() == "v2"
    assert not glob.glob(str(docs / ".delta-restore-*"))


def test_a_whole_folder_can_be_restored_as_a_copy(bus, tmp_path):
    home = tmp_path / "home"
    (home / "proj" / "sub").mkdir(parents=True)
    (home / "proj" / "sub" / "n.txt").write_text("old")
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "bh")})
    repo = Repository(str(tmp_path / "repo"))
    runner.init(repo)
    runner.create(repo, BackupJob("j", (str(home),)), "first")
    (home / "proj" / "sub" / "n.txt").write_text("new")
    service = DeltaService(
        bus,
        SnapshotService(runner, repo),
        JobRunner(bus),
        BackupService(runner, repo, (str(home),)),
        RestoreService(runner, repo, str(home)),
    )
    try:
        _, finished, error = _call(bus, "RestoreAsCopy", "first", str(home / "proj"))
    finally:
        service.unregister()

    assert error is None and finished is not None and finished[1] is True, finished
    copies = glob.glob(str(home / "proj (restored *)"))
    assert len(copies) == 1 and finished[2] == copies[0]
    assert open(copies[0] + "/sub/n.txt").read() == "old"
    assert (home / "proj" / "sub" / "n.txt").read_text() == "new"


def test_restore_replace_keeps_the_version_it_replaces(bus, world):
    docs = world

    _, finished, _ = _call(bus, "RestoreReplace", "first", str(docs / "a.txt"))

    assert finished is not None and finished[1] is True, finished
    assert (docs / "a.txt").read_text() == "v1"
    kept = glob.glob(str(docs / "a (before restore *).txt"))
    assert len(kept) == 1 and open(kept[0]).read() == "v2"


def test_restore_beside_rejects_a_path_outside_home(bus, world, tmp_path):
    _, finished, error = _call(bus, "RestoreAsCopy", "first", str(tmp_path / "elsewhere.txt"))

    assert finished is None
    assert "InvalidPath" in error


def test_restore_beside_of_an_unknown_snapshot_fails_the_job(bus, world):
    docs = world

    _, finished, _ = _call(bus, "RestoreAsCopy", "nope", str(docs / "a.txt"))

    assert finished is not None and finished[1] is False
    assert list(docs.iterdir()) == [docs / "a.txt"]
