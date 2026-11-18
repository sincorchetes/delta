import pytest

from delta.application.backup_notifications import BackupNotifications
from delta.domain.backup_job import BackupJob, JobState
from delta.domain.notification import Notification, NotificationKind
from delta.infrastructure.gio_notifier import MAX_DETAIL, render


class Recorder:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def notify(self, notification):
        if self.fail:
            raise RuntimeError("no notification daemon")
        self.sent.append(notification)


def test_lifecycle_messages():
    recorder = Recorder()
    notes = BackupNotifications(recorder)

    notes.started()
    notes.succeeded()
    notes.warned("1 file unreadable")
    notes.failed("repository locked")
    notes.postponed()

    assert recorder.sent == [
        Notification(NotificationKind.BACKUP_STARTED),
        Notification(NotificationKind.BACKUP_SUCCEEDED),
        Notification(NotificationKind.BACKUP_WARNINGS, "1 file unreadable"),
        Notification(NotificationKind.BACKUP_FAILED, "repository locked"),
        Notification(NotificationKind.BACKUP_POSTPONED),
    ]


def test_a_failing_notifier_never_breaks_the_backup():
    notes = BackupNotifications(Recorder(fail=True))
    notes.started()
    notes.failed("boom")


@pytest.mark.parametrize("kind", list(NotificationKind))
def test_every_kind_renders_title_and_body(kind):
    title, body, _ = render(Notification(kind, "detail"))
    assert title and body


def test_long_details_are_truncated():
    _, body, _ = render(Notification(NotificationKind.BACKUP_FAILED, "x" * 1000))
    assert len(body) <= MAX_DETAIL + 1


def test_failure_without_detail_has_a_default_body():
    _, body, _ = render(Notification(NotificationKind.BACKUP_FAILED))
    assert body


def test_warning_state_is_distinct_from_success_and_failure():
    job = BackupJob("j", ("/home",))
    job.start()
    job.warn("file vanished")
    assert job.state is JobState.WARNINGS and job.message == "file vanished"
    with pytest.raises(ValueError):
        job.fail("again")
