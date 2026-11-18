import pytest

from delta.application.backup_notifications import BackupNotifications
from delta.application.backup_service import BackupService
from delta.daemon.backup_task import make_backup_task
from delta.i18n import _ as translate
from delta.domain.backup_job import BackupJob, JobState
from delta.domain.errors import BackupInterrupted, BackupWarning, EngineError
from delta.domain.repository import Repository
from delta.infrastructure.file_job_journal import FileJobJournal
from delta.infrastructure.gio_notifier import render
from delta.domain.notification import Notification, NotificationKind


class FakeEngine:
    def __init__(self, error=None):
        self.error = error

    def create(self, repo, job, name=None, on_progress=None):
        if self.error:
            raise self.error
        return "archive"


class Recorder:
    def __init__(self):
        self.kinds = []

    def notify(self, notification):
        self.kinds.append(notification.kind.value)


class FakePrune:
    def __init__(self, fail=False):
        self.fail, self.ran = fail, 0

    def run(self):
        self.ran += 1
        if self.fail:
            raise EngineError("prune broke")


def run(tmp_path, error=None, prune=None):
    journal, notifier = FileJobJournal(tmp_path), Recorder()
    backup = BackupService(FakeEngine(error), Repository("/r"), ("/home",))
    job = backup.new_job()
    task = make_backup_task(job, backup, prune, BackupNotifications(notifier), journal)
    result = task(lambda event: None)
    return result, job, journal, notifier


def test_success_clears_the_journal_and_notifies(tmp_path):
    result, job, journal, notifier = run(tmp_path)
    assert result == (True, "")
    assert job.state is JobState.SUCCEEDED
    assert not journal.was_interrupted()
    assert notifier.kinds == ["backup-started", "backup-succeeded"]


def test_interruption_keeps_the_journal_so_it_is_resumed(tmp_path):
    result, job, journal, notifier = run(tmp_path, BackupInterrupted("stop"))
    assert result == (False, translate("interrupted; it will be resumed"))
    assert job.state is JobState.INTERRUPTED
    assert journal.was_interrupted()
    assert notifier.kinds == ["backup-started", "backup-interrupted"]


def test_interruption_does_not_prune(tmp_path):
    prune = FakePrune()
    run(tmp_path, BackupInterrupted("stop"), prune)
    assert prune.ran == 0


def test_real_failure_clears_the_journal_so_it_is_not_retried_forever(tmp_path):
    result, _, journal, notifier = run(tmp_path, EngineError("boom"))
    assert result == (False, "boom")
    assert not journal.was_interrupted()
    assert notifier.kinds == ["backup-started", "backup-failed"]


def test_warnings_count_as_a_backup_and_still_prune(tmp_path):
    prune = FakePrune()
    result, job, journal, notifier = run(tmp_path, BackupWarning("1 unreadable"), prune)
    assert result == (True, "1 unreadable")
    assert job.state is JobState.WARNINGS and prune.ran == 1
    assert not journal.was_interrupted()
    assert notifier.kinds == ["backup-started", "backup-warnings"]


def test_prune_failure_after_a_good_backup_is_reported_as_a_warning(tmp_path):
    result, _, _, notifier = run(tmp_path, prune=FakePrune(fail=True))
    assert result[0] is True and "prune failed" in result[1]
    assert notifier.kinds[-1] == "backup-warnings"


def test_unwritable_journal_does_not_stop_the_backup(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("file")
    backup = BackupService(FakeEngine(), Repository("/r"), ("/home",))
    task = make_backup_task(backup.new_job(), backup, None, None, FileJobJournal(blocker / "state"))
    assert task(lambda event: None) == (True, "")


def test_interrupted_is_a_distinct_final_state():
    job = BackupJob("j", ("/home",))
    job.start()
    job.interrupt()
    assert job.state is JobState.INTERRUPTED
    with pytest.raises(ValueError):
        job.succeed()


def test_journal_marker_round_trip(tmp_path):
    journal = FileJobJournal(tmp_path / "state")
    assert not journal.was_interrupted()
    journal.begin()
    assert FileJobJournal(tmp_path / "state").was_interrupted()
    journal.end()
    journal.end()
    assert not journal.was_interrupted()


def test_interrupted_notification_is_rendered():
    title, body, _ = render(Notification(NotificationKind.BACKUP_INTERRUPTED))
    assert title and body


def test_an_interruption_without_notifications_still_keeps_the_journal(tmp_path):
    journal = FileJobJournal(tmp_path)
    backup = BackupService(FakeEngine(BackupInterrupted("stop")), Repository("/r"), ("/home",))
    task = make_backup_task(backup.new_job(), backup, None, None, journal)

    result = task(lambda event: None)

    assert result == (False, translate("interrupted; it will be resumed"))
    assert journal.was_interrupted()
