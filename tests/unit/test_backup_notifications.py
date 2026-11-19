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


# --- a drive that stays away is told once -------------------------------------------------------


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


def missing():
    from delta.domain.destination import DestinationState
    from delta.domain.errors import DestinationUnavailable

    return DestinationUnavailable("/media/disk/delta", DestinationState.MISSING)


def absent_notes():
    recorder, clock = Recorder(), Clock()
    return BackupNotifications(recorder, clock), recorder, clock


def test_the_hourly_tries_while_the_drive_is_away_tell_it_once():
    notes, recorder, clock = absent_notes()

    for _hour in range(24):
        notes.destination_unavailable(missing())
        clock.now += 3600

    assert [n.kind for n in recorder.sent] == [NotificationKind.DESTINATION_UNAVAILABLE]


def test_a_week_later_it_is_a_reminder():
    from delta.application.backup_notifications import REMINDER_AFTER

    notes, recorder, clock = absent_notes()
    notes.destination_unavailable(missing())
    clock.now += REMINDER_AFTER - 1
    notes.destination_unavailable(missing())
    clock.now += 1
    notes.destination_unavailable(missing())

    assert len(recorder.sent) == 2


def test_a_good_backup_ends_the_absence_so_the_next_one_is_told_again():
    notes, recorder, clock = absent_notes()
    notes.destination_unavailable(missing())
    notes.succeeded()
    notes.destination_unavailable(missing())

    assert [n.kind for n in recorder.sent].count(NotificationKind.DESTINATION_UNAVAILABLE) == 2


def test_a_backup_with_warnings_also_ends_the_absence():
    notes, recorder, _clock = absent_notes()
    notes.destination_unavailable(missing())
    notes.warned("1 unreadable")
    notes.destination_unavailable(missing())

    assert [n.kind for n in recorder.sent].count(NotificationKind.DESTINATION_UNAVAILABLE) == 2


def test_a_drive_lost_during_a_backup_always_replaces_the_one_in_progress_and_counts_as_told():
    notes, recorder, _clock = absent_notes()
    notes.destination_unavailable(missing())

    notes.destination_lost(missing())
    notes.destination_unavailable(missing())

    assert len(recorder.sent) == 2
