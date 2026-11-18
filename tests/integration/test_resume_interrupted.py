import threading
import time

from conftest import call_and_wait_finished
from gi.repository import GLib

from delta.application.backup_service import BackupService
from delta.application.snapshot_service import SnapshotService
from delta.daemon.job_runner import JobRunner
from delta.daemon.service import DeltaService
from delta.domain.repository import Repository
from delta.infrastructure.file_job_journal import FileJobJournal


class FakeEngine:
    def __init__(self):
        self.created = []

    def create(self, repo, job, name=None, on_progress=None):
        self.created.append(job.id)
        return "archive"

    def list_snapshots(self, repo):
        return []


def wait_until(predicate, timeout=5.0):
    context, deadline = GLib.MainContext.default(), time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)
    return predicate()


def make(bus, tmp_path):
    engine, repo = FakeEngine(), Repository("/r")
    journal = FileJobJournal(tmp_path / "state")
    service = DeltaService(
        bus,
        SnapshotService(engine, repo),
        JobRunner(bus),
        BackupService(engine, repo, ("/home",)),
        journal=journal,
    )
    return engine, journal, service


def test_interrupted_backup_is_resumed_and_the_mark_cleared(bus, tmp_path):
    engine, journal, service = make(bus, tmp_path)
    journal.begin()

    started = service.resume_interrupted()

    assert started is True
    assert wait_until(lambda: not journal.was_interrupted())
    assert len(engine.created) == 1
    service.unregister()


def test_no_valid_sources_is_a_controlled_error_not_a_hang(bus, tmp_path):
    engine, repo = FakeEngine(), Repository("/r")
    service = DeltaService(
        bus,
        SnapshotService(engine, repo),
        JobRunner(bus),
        BackupService(engine, repo, ()),
        journal=FileJobJournal(tmp_path / "state"),
    )

    # Async call: the service lives on this same connection, so a blocking call would deadlock.
    job_id, finished, error = call_and_wait_finished(bus, "CreateBackup", timeout_ms=5000)
    service.unregister()

    assert job_id is None and finished is None
    assert error is not None and "InvalidArgument" in error
    assert engine.created == []


def test_nothing_is_resumed_without_an_interruption(bus, tmp_path):
    engine, _, service = make(bus, tmp_path)

    assert service.resume_interrupted() is False
    assert engine.created == []
    service.unregister()


def test_resume_does_not_start_a_second_job_while_busy(bus, tmp_path):
    release = threading.Event()
    engine, journal, service = make(bus, tmp_path)
    engine.create = lambda repo, job, name=None, on_progress=None: release.wait(5) and "a"
    journal.begin()
    assert service.resume_interrupted() is True

    assert service.resume_interrupted() is False

    release.set()
    assert wait_until(lambda: not journal.was_interrupted())
    service.unregister()
