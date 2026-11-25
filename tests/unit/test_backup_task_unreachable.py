"""A backup task whose destination cannot be reached, and what each notification says."""

import logging

import pytest

from delta.application.backup_notifications import BackupNotifications
from delta.application.backup_service import BackupService
from delta.daemon.backup_task import make_backup_task
from delta.i18n import _ as translate
from delta.domain.backup_job import JobState
from delta.domain.destination import DestinationState
from delta.domain.errors import BackupWarning, DestinationUnavailable, EngineError
from delta.domain.repository import Repository
from delta.infrastructure.file_job_journal import FileJobJournal
from delta.infrastructure.gio_notifier import render
from delta.domain.notification import Notification, NotificationKind
from gi.repository import Gio
from backup_task_support import FakeEngine, FakePrune, Recorder, run


# --- a destination that cannot be reached ---------------------------------------------------------


class Journal:
    def __init__(self):
        self.begun = self.ended = 0

    def begin(self):
        self.begun += 1

    def end(self):
        self.ended += 1


class Probe:
    def __init__(self, *states):
        self.states, self.asked = list(states), []

    def state(self, repo, out_of_space=False):
        self.asked.append(repo)
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]


def waiting(error, *states):

    journal, notifier = Journal(), Recorder()
    probe = Probe(*(getattr(DestinationState, state) for state in states))
    backup = BackupService(FakeEngine(error), Repository("/media/disk/delta"), ("/home",), destination=probe)
    job = backup.new_job()
    task = make_backup_task(job, backup, FakePrune(), BackupNotifications(notifier), journal)
    return task, job, journal, notifier


def test_a_drive_that_is_not_there_starts_nothing_and_is_told_without_a_backup_in_progress(tmp_path):

    task, job, journal, notifier = waiting(None, "MISSING")

    with pytest.raises(DestinationUnavailable) as raised:
        task(lambda event: None)

    assert raised.value.location == "/media/disk/delta"
    assert job.unavailable is raised.value  # the reason is kept on the job, not lost on the way up
    assert job.state is JobState.UNAVAILABLE
    assert (journal.begun, journal.ended) == (0, 0)
    assert notifier.kinds == ["destination-unavailable"]  # and no "backup in progress" to take back


def test_a_drive_that_goes_while_the_engine_works_replaces_the_notification_of_the_start():

    # the task asks (and tells the service so), then the service asks again when the engine fails
    task, job, journal, notifier = waiting(EngineError("Input/output error"), "AVAILABLE", "MISSING")

    with pytest.raises(DestinationUnavailable):
        task(lambda event: None)

    assert job.state is JobState.UNAVAILABLE
    assert notifier.kinds == ["backup-started", "destination-unavailable"]
    assert (journal.begun, journal.ended) == (1, 1)  # it is not resumed: there is nothing to resume at a drive that is gone


def test_a_failure_with_the_drive_there_is_still_told_as_a_failure():
    task, job, journal, notifier = waiting(EngineError("it broke"), "AVAILABLE")

    result = task(lambda event: None)

    assert result == (False, "it broke") and job.state is JobState.FAILED
    assert notifier.kinds == ["backup-started", "backup-failed"]


def test_the_notification_of_a_drive_that_is_not_connected_says_what_to_do_and_is_not_an_alarm():

    error = DestinationUnavailable("/media/disk/delta", DestinationState.MISSING)
    title, body, priority = render(Notification(NotificationKind.DESTINATION_UNAVAILABLE, error.hint))

    assert title == translate("Backup drive not connected") and body == error.hint
    assert priority == Gio.NotificationPriority.NORMAL
    assert render(Notification(NotificationKind.DESTINATION_UNAVAILABLE))[1] == translate(
        "Connect the drive that holds your backups."
    )


def test_a_drive_that_goes_while_the_engine_works_is_still_unavailable_without_notifications():
    probe = Probe(DestinationState.AVAILABLE, DestinationState.MISSING)
    backup = BackupService(FakeEngine(EngineError("Input/output error")), Repository("/media/disk/delta"), ("/home",), destination=probe)
    job = backup.new_job()
    task = make_backup_task(job, backup, None, None, None)

    with pytest.raises(DestinationUnavailable):
        task(lambda event: None)

    assert job.state is JobState.UNAVAILABLE


def test_a_drive_that_is_not_there_waits_without_notifications_too():
    backup = BackupService(FakeEngine(), Repository("/media/disk/delta"), ("/home",), destination=Probe(DestinationState.MISSING))
    job = backup.new_job()
    task = make_backup_task(job, backup, None, None, None)

    with pytest.raises(DestinationUnavailable):
        task(lambda event: None)

    assert job.state is JobState.UNAVAILABLE


def test_the_probe_is_asked_about_the_repository_of_the_backup_and_the_error_says_where_it_is():
    probe = Probe(DestinationState.EMPTY)
    backup = BackupService(FakeEngine(), Repository("/media/disk/delta"), ("/home",), destination=probe)

    error = backup.unreachable("")

    assert probe.asked == [Repository("/media/disk/delta")]
    assert (error.location, error.state) == ("/media/disk/delta", DestinationState.EMPTY)


def test_with_nothing_to_probe_with_or_no_repository_nothing_is_unreachable():
    assert BackupService(FakeEngine(), Repository("/r"), ("/home",)).unreachable("") is None
    assert BackupService(FakeEngine(), None, ("/home",), destination=Probe(DestinationState.MISSING)).unreachable("") is None


# --- what each notification says, what the service is handed, and what is logged -----------------------


def test_a_failure_is_told_with_its_reason(tmp_path):
    _, _, _, notifier = run(tmp_path, EngineError("boom"))

    assert notifier.sent[-1] == Notification(NotificationKind.BACKUP_FAILED, "boom")


def test_a_warning_is_told_with_what_the_engine_said(tmp_path):
    _, _, _, notifier = run(tmp_path, BackupWarning("1 unreadable"))

    assert notifier.sent[-1] == Notification(NotificationKind.BACKUP_WARNINGS, "1 unreadable")


def test_a_prune_that_fails_is_told_with_its_own_error_in_the_message(tmp_path):
    result, _, _, notifier = run(tmp_path, prune=FakePrune(fail=True))

    expected = "backup done, prune failed: prune broke"
    assert result == (True, expected)
    assert notifier.sent[-1] == Notification(NotificationKind.BACKUP_WARNINGS, expected)


def test_the_service_is_handed_the_job_the_progress_callback_and_that_it_was_already_asked():
    seen = []

    class Spy(BackupService):
        def run(self, job, on_progress=None, checked=False):
            seen.append((job, on_progress, checked))
            return super().run(job, on_progress, checked)

    backup = Spy(FakeEngine(), Repository("/r"), ("/home",))
    job = backup.new_job()

    def progress(event):
        pass

    make_backup_task(job, backup, None, None, None)(progress)

    assert seen == [(job, progress, True)]


def test_a_journal_that_cannot_be_written_is_logged_with_its_error(tmp_path, caplog):
    blocker = tmp_path / "blocker"
    blocker.write_text("file")
    backup = BackupService(FakeEngine(), Repository("/r"), ("/home",))

    with caplog.at_level(logging.WARNING, logger="delta.daemon.backup_task"):
        make_backup_task(backup.new_job(), backup, None, None, FileJobJournal(blocker / "state"))(lambda event: None)

    with pytest.raises(OSError) as raised:
        FileJobJournal(blocker / "state").begin()
    messages = [record.getMessage() for record in caplog.records if record.name == "delta.daemon.backup_task"]
    assert "cannot update the backup journal: " + str(raised.value) in messages
