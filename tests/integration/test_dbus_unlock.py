import shutil

import pytest
from conftest import call_and_wait_finished

from delta.application.snapshot_service import SnapshotService
from delta.application.unlock_service import UnlockService
from delta.daemon.job_runner import JobRunner
from delta.daemon.service import DeltaService
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


class MemoryStore:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, secret):
        self.data[key] = secret

    def delete(self, key):
        self.data.pop(key, None)


def test_unlocking_a_healthy_repository_succeeds_and_forgets_the_old_failure(bus, tmp_path):
    store = MemoryStore()
    runner = BorgRunner(env={"BORG_BASE_DIR": str(tmp_path / "bh")}, secrets=store)
    repo = Repository(str(tmp_path / "repo"))
    store.data[repo.location] = "pw"
    runner.init(repo)
    jobs = JobRunner(bus)
    jobs.last_error = "Failed to create/acquire the lock (timeout)."
    service = DeltaService(
        bus, SnapshotService(runner, repo), jobs, unlock=UnlockService(runner, repo)
    )

    _, finished, error = call_and_wait_finished(bus, "UnlockRepository", None)
    service.unregister()

    assert error is None and finished is not None and finished[1] is True, finished
    assert jobs.last_error == ""


def test_without_a_repository_the_user_is_told_so(bus):
    jobs = JobRunner(bus)
    service = DeltaService(bus, SnapshotService(None, None), jobs, unlock=UnlockService(None, None))

    _, finished, _ = call_and_wait_finished(bus, "UnlockRepository", None)
    service.unregister()

    assert finished is not None and finished[1] is False and finished[2]
