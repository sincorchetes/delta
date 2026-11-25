"""What the tests of test_backup_task share."""

from delta.application.backup_notifications import BackupNotifications
from delta.application.backup_service import BackupService
from delta.daemon.backup_task import make_backup_task
from delta.domain.errors import EngineError
from delta.domain.repository import Repository
from delta.infrastructure.file_job_journal import FileJobJournal


class FakeEngine:
    def __init__(self, error=None):
        self.error = error

    def create(self, repo, job, name=None, on_progress=None):
        if self.error:
            raise self.error
        return "archive"


class Recorder:
    def __init__(self):
        self.kinds, self.sent = [], []

    def notify(self, notification):
        self.kinds.append(notification.kind.value)
        self.sent.append(notification)


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
