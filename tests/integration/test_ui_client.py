import time

from gi.repository import GLib

from delta.application.backup_service import BackupService
from delta.application.snapshot_service import SnapshotService
from delta.daemon.job_runner import JobRunner
from delta.daemon.service import DeltaService
from delta.domain.errors import EngineError
from delta.domain.repository import Repository
from delta.ui.client import DeltaClient, readable


class FakeEngine:
    def __init__(self, error=None):
        self.error = error

    def create(self, repo, job, name=None, on_progress=None):
        if self.error:
            raise self.error
        return "archive"

    def list_snapshots(self, repo):
        return []


def wait_for(box, timeout=5.0):
    context, deadline = GLib.MainContext.default(), time.monotonic() + timeout
    while not box and time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)
    return box


def serve(bus, engine=None, repo="/r"):
    engine = engine or FakeEngine()
    repository = Repository(repo) if repo else None
    return DeltaService(
        bus,
        SnapshotService(engine, repository),
        JobRunner(bus),
        BackupService(engine, repository, ("/home",)),
    )


def client_for(bus):
    """The service lives on this connection, which has a unique name but owns no well-known one."""
    return DeltaClient(bus, bus.get_unique_name())


def ask(call):
    box = []
    call(lambda value, error: box.append((value, error)))
    return wait_for(box)[0]


def test_read_state_returns_the_daemons_properties(bus):
    service = serve(bus)

    value, error = ask(client_for(bus).read_state)
    service.unregister()

    assert error is None
    assert value["Status"] == "idle" and value["LastBackup"] == 0 and value["LastError"] == "" and value["UnavailableReason"] == ""


def test_a_failed_backup_is_reported_through_signal_and_property(bus):
    service = serve(bus, FakeEngine(EngineError("repository exploded")))
    client = client_for(bus)
    finished = []
    client.on_backup_finished(lambda job, ok, message: finished.append((job, ok, message)))

    job_id, error = ask(client.create_backup)
    wait_for(finished)
    state, _ = ask(client.read_state)
    service.unregister()

    assert error is None and finished and finished[0][0] == job_id
    assert finished[0][1] is False and "repository exploded" in finished[0][2]
    assert "repository exploded" in state["LastError"]


def test_a_good_backup_clears_the_error_and_records_the_time(bus):
    service = serve(bus)
    client = client_for(bus)
    finished = []
    client.on_backup_finished(lambda job, ok, message: finished.append(ok))

    ask(client.create_backup)
    wait_for(finished)
    state, _ = ask(client.read_state)
    service.unregister()

    assert finished == [True]
    assert state["LastError"] == "" and state["LastBackup"] > 0


def test_daemon_errors_arrive_as_plain_messages(bus):
    service = serve(bus, repo="")
    box = []
    client_for(bus).create_repository("", "", lambda value, error: box.append((value, error)))
    value, error = wait_for(box)[0]
    service.unregister()

    assert value is None and error
    assert "GDBus.Error" not in error


def test_readable_strips_the_remote_error_prefix():
    class Fake:
        message = "GDBus.Error:io.github.sincorchetes.Delta.Service1.Error.Busy: another job is already running"

    assert readable(Fake()) == "another job is already running"


def test_unsubscribing_stops_deliveries(bus):
    service = serve(bus)
    client = client_for(bus)
    seen = []
    subscription = client.on_backup_finished(lambda *args: seen.append(args))
    client.unsubscribe(subscription)

    ask(client.create_backup)
    time.sleep(0.2)
    GLib.MainContext.default().iteration(False)
    service.unregister()

    assert seen == []
