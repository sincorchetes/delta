import os
import shutil

import pytest
from dbus_helpers import call_and_wait_finished

from delta.application.backup_notifications import BackupNotifications
from delta.application.backup_service import BackupService
from delta.application.prune_service import PruneService
from delta.application.snapshot_service import SnapshotService
from delta.domain.backup_job import BackupJob
from delta.domain.retention import RetentionPolicy
from delta.daemon.job_runner import JobRunner
from delta.daemon.service import DeltaService
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


def _setup(bus, tmp_path, repo_path):
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "bh")})
    repo = Repository(str(repo_path))
    data = tmp_path / "data"
    data.mkdir()
    (data / "f").write_text("hi")
    service = DeltaService(
        bus,
        SnapshotService(runner, repo),
        JobRunner(bus),
        BackupService(runner, repo, (str(data),)),
    )
    return runner, repo, service


def test_create_backup_emits_finished_and_creates_snapshot(bus, tmp_path):
    runner, repo, service = _setup(bus, tmp_path, tmp_path / "repo")
    runner.init(repo)

    job_id, finished, error = call_and_wait_finished(bus, "CreateBackup")
    service.unregister()

    assert error is None and finished is not None
    assert finished[0] == job_id
    assert finished[1] is True, finished[2]
    assert len(runner.list_snapshots(repo)) == 1


def test_successful_backup_prunes_with_retention_policy(bus, tmp_path):
    runner, repo, service = _setup(bus, tmp_path, tmp_path / "repo")
    runner.init(repo)
    service.unregister()
    data = tmp_path / "data"
    runner.create(repo, BackupJob("old", (str(data),)), "old")
    service = DeltaService(
        bus,
        SnapshotService(runner, repo),
        JobRunner(bus),
        BackupService(runner, repo, (str(data),)),
        prune=PruneService(runner, repo, RetentionPolicy(1, 0, 0, 0)),
    )

    _, finished, _ = call_and_wait_finished(bus, "CreateBackup")
    service.unregister()

    assert finished is not None and finished[1] is True, finished
    assert len(runner.list_snapshots(repo)) == 1


class RecordingNotifier:
    def __init__(self):
        self.kinds = []

    def notify(self, notification):
        self.kinds.append(notification.kind.value)


def _notifying_service(bus, tmp_path, repo_path, data):
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "bh")})
    repo = Repository(str(repo_path))
    notifier = RecordingNotifier()
    service = DeltaService(
        bus,
        SnapshotService(runner, repo),
        JobRunner(bus),
        BackupService(runner, repo, (str(data),)),
        notifications=BackupNotifications(notifier),
    )
    return runner, repo, service, notifier


def test_successful_backup_notifies_started_then_succeeded(bus, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "f").write_text("hi")
    runner, repo, service, notifier = _notifying_service(bus, tmp_path, tmp_path / "repo", data)
    runner.init(repo)

    _, finished, _ = call_and_wait_finished(bus, "CreateBackup")
    service.unregister()

    assert finished is not None and finished[1] is True
    assert notifier.kinds == ["backup-started", "backup-succeeded"]


def test_failed_backup_notifies_started_then_failed(bus, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "f").write_text("hi")
    _, _, service, notifier = _notifying_service(bus, tmp_path, tmp_path / "missing", data)

    _, finished, _ = call_and_wait_finished(bus, "CreateBackup")
    service.unregister()

    assert finished is not None and finished[1] is False
    assert notifier.kinds == ["backup-started", "backup-failed"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read everything")
def test_unreadable_file_is_a_warning_and_still_creates_the_snapshot(bus, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "ok").write_text("hi")
    secret = data / "unreadable"
    secret.write_text("no")
    secret.chmod(0)
    runner, repo, service, notifier = _notifying_service(bus, tmp_path, tmp_path / "repo", data)
    runner.init(repo)

    try:
        _, finished, _ = call_and_wait_finished(bus, "CreateBackup")
    finally:
        service.unregister()
        secret.chmod(0o600)

    assert finished is not None and finished[1] is True, finished
    assert finished[2]
    assert len(runner.list_snapshots(repo)) == 1
    assert notifier.kinds == ["backup-started", "backup-warnings"]


def test_failed_backup_reports_error(bus, tmp_path):
    _, _, service = _setup(bus, tmp_path, tmp_path / "missing-repo")

    _, finished, _ = call_and_wait_finished(bus, "CreateBackup")
    service.unregister()

    assert finished is not None
    assert finished[1] is False
    assert finished[2]
