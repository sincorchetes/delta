import shutil

import gi
import pytest

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from delta.application.snapshot_service import SnapshotService
from delta.daemon.service import DeltaService
from delta.domain.backup_job import BackupJob
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


def _call_list_snapshots(bus):
    loop = GLib.MainLoop()
    outcome = {}

    def done(connection, result):
        try:
            outcome["value"] = connection.call_finish(result).unpack()
        except GLib.Error as err:
            outcome["error"] = err.message
        loop.quit()

    bus.call(
        bus.get_unique_name(), "/io/github/sincorchetes/Delta/Service1", "io.github.sincorchetes.Delta.Service1", "ListSnapshots",
        None, None, Gio.DBusCallFlags.NONE, 5000, None, done,
    )
    GLib.timeout_add(8000, loop.quit)
    loop.run()
    return outcome


def test_list_snapshots_over_dbus(bus, tmp_path):
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "bh")})
    repo = Repository(str(tmp_path / "repo"))
    runner.init(repo)
    data = tmp_path / "data"
    data.mkdir()
    (data / "f").write_text("hi")
    runner.create(repo, BackupJob("j", (str(data),)), "one")

    service = DeltaService(bus, SnapshotService(runner, repo))
    outcome = _call_list_snapshots(bus)
    service.unregister()

    (rows,) = outcome["value"]
    assert [row["name"] for row in rows] == ["one"]


def test_no_repository_returns_empty_list(bus):
    service = DeltaService(bus, SnapshotService(BorgRunner(), None))
    outcome = _call_list_snapshots(bus)
    service.unregister()
    assert outcome["value"] == ([],)
