import os
import shutil

import pytest

from delta.application.backup_service import BackupService
from delta.domain.backup_job import BackupJob, JobState
from delta.domain.errors import BackupInterrupted
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


@pytest.fixture
def world(tmp_path):
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "bh")})
    repo = Repository(str(tmp_path / "repo"))
    runner.init(repo)
    data = tmp_path / "data"
    data.mkdir()
    (data / "big.bin").write_bytes(os.urandom(64 * 1024 * 1024))
    return runner, repo, BackupJob("j", (str(data),))


def test_interrupt_stops_borg_cleanly_and_the_next_backup_works(world):
    runner, repo, job = world
    fired = []

    def on_progress(event):
        if not fired:
            fired.append(event)
            runner.interrupt()

    with pytest.raises(BackupInterrupted):
        runner.create(repo, job, "first", on_progress=on_progress)

    assert fired
    assert runner.list_snapshots(repo) == []
    runner.create(repo, job, "second")
    assert [s.name for s in runner.list_snapshots(repo)] == ["second"]


def test_interruption_marks_the_job_interrupted_not_failed(world):
    runner, repo, job = world
    service = BackupService(runner, repo, job.sources)
    stopped = []

    def on_progress(event):
        if not stopped:
            stopped.append(True)
            runner.interrupt()

    result = service.run(service.new_job(), on_progress)

    assert result.state is JobState.INTERRUPTED


def test_interrupt_without_a_running_process_is_harmless(world):
    runner, repo, job = world
    runner.interrupt()
    runner.create(repo, job, "after")
    assert [s.name for s in runner.list_snapshots(repo)] == ["after"]
