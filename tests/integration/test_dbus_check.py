import shutil

import pytest
from dbus_helpers import IFACE, PATH, call_and_wait_finished
from gi.repository import Gio, GLib

from delta.application.check_service import CheckService
from delta.application.snapshot_service import SnapshotService
from delta.daemon.job_runner import JobRunner
from delta.daemon.service import DeltaService
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner
from delta.infrastructure.local_destination import LocalDestination

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


class MemoryStore:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, secret):
        self.data[key] = secret

    def delete(self, key):
        self.data.pop(key, None)


def call_without_result(bus, method):
    """Call a method that answers with nothing; returns the error text, or None."""
    loop, outcome = GLib.MainLoop(), {}

    def done(connection, result):
        try:
            connection.call_finish(result)
        except GLib.Error as err:
            outcome["error"] = err.message
        loop.quit()

    bus.call(bus.get_unique_name(), PATH, IFACE, method, None, None, Gio.DBusCallFlags.NONE, 5000, None, done)
    GLib.timeout_add(15000, loop.quit)
    loop.run()
    return outcome.get("error")


def serve(bus, tmp_path):
    store = MemoryStore()
    runner = BorgRunner(env={"BORG_BASE_DIR": str(tmp_path / "bh")}, secrets=store)
    repo = Repository(str(tmp_path / "repo"))
    store.data[repo.location] = "pw"
    runner.init(repo)
    jobs = JobRunner(bus)
    service = DeltaService(
        bus,
        SnapshotService(runner, repo),
        jobs,
        check=CheckService(runner, repo, LocalDestination()),
        on_cancel=runner.interrupt,
    )
    return service, jobs


def test_checking_a_sound_repository_ends_well_and_says_so(bus, tmp_path):
    service, jobs = serve(bus, tmp_path)

    _, finished, error = call_and_wait_finished(bus, "CheckRepository", None)
    service.unregister()

    assert error is None and finished is not None, finished
    assert finished[1:] == (True, "Your backups were checked and no problems were found.")
    assert jobs.status == "idle"


def test_cancelling_with_no_check_running_does_nothing(bus, tmp_path):
    service, jobs = serve(bus, tmp_path)

    error = call_without_result(bus, "CancelCheck")
    service.unregister()

    assert error is None and jobs.status == "idle"


def test_without_the_check_the_call_is_unavailable(bus):
    service = DeltaService(bus, SnapshotService(None, None), JobRunner(bus))

    _, _finished, error = call_and_wait_finished(bus, "CheckRepository", None)
    service.unregister()

    assert error is not None and "not available" in error
