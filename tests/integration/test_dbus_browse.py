"""Opening a snapshot over the real bus: the backup steps aside, waits, and comes back once it is closed."""

import os
import time
from datetime import datetime

from conftest import IFACE, PATH, call_and_wait_finished
from gi.repository import Gio, GLib

from delta.application.backup_service import BackupService
from delta.application.browse_service import BrowseService
from delta.application.snapshot_service import SnapshotService
from delta.daemon.browse_controller import BrowseController
from delta.daemon.job_runner import JobRunner
from delta.daemon.service import DeltaService
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot


class Engine:
    def __init__(self):
        self.created, self.interrupts = [], 0

    def list_snapshots(self, repo):
        return [Snapshot("id1", "snap1", datetime(2026, 1, 1))]

    def create(self, repo, job, name=None, on_progress=None):
        self.created.append(job.id)
        return "archive"

    def interrupt(self):
        self.interrupts += 1


class Mounter:
    def __init__(self):
        self.mounted, self.unmounted = [], []

    def mount(self, repo, snapshot, mountpoint):
        self.mounted.append((snapshot, mountpoint))

    def unmount(self, mountpoint):
        self.unmounted.append(mountpoint)


def wait_until(predicate, timeout=5.0):
    context, deadline = GLib.MainContext.default(), time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)
    return predicate()


def make(bus, tmp_path):
    engine, mounter, repo = Engine(), Mounter(), Repository("/r")
    jobs = JobRunner(bus)
    box = {}
    control = BrowseController(bus, jobs, engine.interrupt, lambda owed: box["service"].resume_interrupted(owed))
    box["service"] = DeltaService(
        bus,
        SnapshotService(engine, repo),
        jobs,
        BackupService(engine, repo, ("/home",)),
        browse=BrowseService(engine, mounter, repo, str(tmp_path / "browse")),
        browse_control=control,
    )
    return engine, mounter, box["service"]


def test_a_scheduled_backup_waits_for_the_open_snapshot_and_runs_when_it_closes(bus, tmp_path):
    engine, mounter, service = make(bus, tmp_path)
    folder = str(tmp_path / "browse" / "snapshot")

    job_id, finished, error = call_and_wait_finished(bus, "MountSnapshot", GLib.Variant("(s)", ("id1",)))
    assert error is None and finished == (job_id, True, folder)
    assert mounter.mounted == [("snap1", folder)]
    assert service._on_get_property(None, None, None, None, "CanMount").unpack() is True
    assert service._on_get_property(None, None, None, None, "Status").unpack() == "browsing"

    _, _, refused = call_and_wait_finished(bus, "CreateBackup")
    assert "Busy" in refused and engine.created == []

    job_id, finished, error = call_and_wait_finished(bus, "UnmountSnapshot")
    assert error is None and finished == (job_id, True, "")
    assert mounter.unmounted == [folder]
    assert wait_until(lambda: len(engine.created) == 1)  # the backup that was turned away
    assert wait_until(lambda: service._on_get_property(None, None, None, None, "Status").unpack() == "idle")
    service.unregister()


def test_a_window_that_disappears_takes_its_snapshot_with_it(bus, tmp_path):
    engine, mounter, service = make(bus, tmp_path)
    window = Gio.DBusConnection.new_for_address_sync(
        os.environ["DBUS_SESSION_BUS_ADDRESS"],
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None,
        None,
    )
    reply = {}
    window.call(
        bus.get_unique_name(), PATH, IFACE, "MountSnapshot", GLib.Variant("(s)", ("id1",)), None,
        Gio.DBusCallFlags.NONE, 5000, None, lambda c, result: reply.update(job=c.call_finish(result).unpack()),
    )
    assert wait_until(lambda: mounter.mounted and reply)
    assert wait_until(lambda: service._browse_control._watch_id)  # the window is being watched

    window.close_sync(None)

    assert wait_until(lambda: mounter.unmounted)
    service.unregister()
