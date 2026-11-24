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


def test_a_drive_lost_during_a_backup_counts_as_told_so_the_next_try_does_not_tell_again():
    notes, recorder, _clock = absent_notes()

    notes.destination_lost(missing())
    notes.destination_unavailable(missing())

    assert len(recorder.sent) == 1


def test_a_drive_lost_during_a_backup_is_always_told_even_when_it_was_told_before():
    notes, recorder, _clock = absent_notes()
    notes.destination_unavailable(missing())

    notes.destination_lost(missing())

    assert len(recorder.sent) == 2


def test_what_is_told_of_a_drive_is_its_kind_and_what_to_do():
    error = missing()
    notes, recorder, _clock = absent_notes()

    notes.destination_unavailable(error)
    notes.destination_lost(error)

    expected = Notification(NotificationKind.DESTINATION_UNAVAILABLE, error.hint)
    assert recorder.sent == [expected, expected]


# --- each cause is told, and another cause is news -----------------------------------------------------


def of(state):
    from delta.domain.destination import DestinationState
    from delta.domain.errors import DestinationUnavailable

    return DestinationUnavailable("/media/disk/delta", DestinationState(state))


@pytest.mark.parametrize(
    "state, kind",
    [
        ("missing", NotificationKind.DESTINATION_UNAVAILABLE),
        ("empty", NotificationKind.DESTINATION_UNAVAILABLE),
        ("other-drive", NotificationKind.DESTINATION_OTHER_DRIVE),
        ("io-error", NotificationKind.DESTINATION_IO_ERROR),
        ("other-repository", NotificationKind.DESTINATION_OTHER_REPOSITORY),
        ("full", NotificationKind.DESTINATION_FULL),
        ("read-only", NotificationKind.DESTINATION_READ_ONLY),
        ("denied", NotificationKind.DESTINATION_DENIED),
    ],
)
def test_each_cause_is_told_with_its_own_kind_and_its_hint(state, kind):
    notes, recorder, _clock = absent_notes()
    error = of(state)

    notes.destination_unavailable(error)

    assert recorder.sent == [Notification(kind, error.hint)]


def test_a_place_that_is_full_for_days_is_told_once_not_every_hour():
    notes, recorder, clock = absent_notes()

    for _hour in range(24):
        notes.destination_unavailable(of("full"))
        clock.now += 3600

    assert len(recorder.sent) == 1


def test_another_cause_is_news_even_before_the_reminder():
    notes, recorder, clock = absent_notes()
    notes.destination_unavailable(of("missing"))
    clock.now += 3600

    notes.destination_unavailable(of("full"))
    notes.destination_unavailable(of("full"))

    assert [n.kind for n in recorder.sent] == [
        NotificationKind.DESTINATION_UNAVAILABLE,
        NotificationKind.DESTINATION_FULL,
    ]


@pytest.mark.parametrize("state", ["other-drive", "io-error", "other-repository", "full", "read-only", "denied"])
def test_the_notification_of_each_cause_has_a_title_and_is_not_an_alarm(state):
    from gi.repository import Gio

    error = of(state)
    kind = {
        "other-drive": NotificationKind.DESTINATION_OTHER_DRIVE,
        "io-error": NotificationKind.DESTINATION_IO_ERROR,
        "other-repository": NotificationKind.DESTINATION_OTHER_REPOSITORY,
        "full": NotificationKind.DESTINATION_FULL,
        "read-only": NotificationKind.DESTINATION_READ_ONLY,
        "denied": NotificationKind.DESTINATION_DENIED,
    }[state]

    title, body, priority = render(Notification(kind, error.hint))

    assert title and body == error.hint and priority == Gio.NotificationPriority.NORMAL
    assert render(Notification(kind))[1]  # and a body of its own when there is no detail
