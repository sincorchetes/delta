import pytest

from delta.application.backup_notifications import BackupNotifications
from delta.application.backup_service import BackupService
from delta.daemon.backup_task import make_backup_task
from delta.i18n import _ as translate
from delta.domain.backup_job import BackupJob, JobState
from delta.domain.destination import DestinationState
from delta.domain.errors import BackupInterrupted, BackupWarning, DestinationUnavailable, EngineError
from delta.domain.repository import Repository
from delta.infrastructure.file_job_journal import FileJobJournal
from delta.infrastructure.gio_notifier import render
from delta.domain.notification import Notification, NotificationKind
from gi.repository import Gio


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
    assert job.state is JobState.UNAVAILABLE
    assert (journal.begun, journal.ended) == (0, 0)
    assert notifier.kinds == ["destination-unavailable"]  # and no "backup in progress" to take back


def test_a_drive_that_goes_while_the_engine_works_replaces_the_notification_of_the_start():

    # the task asks, then the service asks, then the service asks again when the engine fails
    task, job, journal, notifier = waiting(EngineError("Input/output error"), "AVAILABLE", "AVAILABLE", "MISSING")

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
    probe = Probe(DestinationState.AVAILABLE, DestinationState.AVAILABLE, DestinationState.MISSING)
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

    error = backup.unreachable()

    assert probe.asked == [Repository("/media/disk/delta")]
    assert (error.location, error.state) == ("/media/disk/delta", DestinationState.EMPTY)


def test_with_nothing_to_probe_with_or_no_repository_nothing_is_unreachable():
    assert BackupService(FakeEngine(), Repository("/r"), ("/home",)).unreachable() is None
    assert BackupService(FakeEngine(), None, ("/home",), destination=Probe(DestinationState.MISSING)).unreachable() is None
