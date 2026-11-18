import os
import shutil
import stat

import pytest
from conftest import IFACE, PATH, call_and_wait_finished
from gi.repository import Gio, GLib

from delta.application.preview_service import PreviewService
from delta.application.snapshot_service import SnapshotService
from delta.daemon.job_runner import JobRunner
from delta.daemon.service import DeltaService
from delta.domain.backup_job import BackupJob
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


@pytest.fixture
def world(bus, tmp_path):
    home = tmp_path / "home"
    (home / "proj" / "sub").mkdir(parents=True)
    (home / "proj" / "sub" / "n.txt").write_text("old")
    (home / "a.txt").write_text("v1")
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "bh")})
    repo = Repository(str(tmp_path / "repo"))
    runner.init(repo)
    runner.create(repo, BackupJob("j", (str(home),)), "first")
    (home / "a.txt").write_text("v2")
    (home / "proj" / "sub" / "n.txt").write_text("new")
    root = tmp_path / "run" / "preview"
    service = DeltaService(
        bus,
        SnapshotService(runner, repo),
        JobRunner(bus),
        preview=PreviewService(runner, repo, str(home), str(root)),
    )
    yield home, root
    service.unregister()
    for folder, _, _ in os.walk(root):  # previews are read-only: let pytest clean up
        os.chmod(folder, 0o700)


def _preview(bus, path):
    return call_and_wait_finished(bus, "PreviewVersion", GLib.Variant("(ss)", ("first", path)))


def _clear(bus):
    loop, outcome = GLib.MainLoop(), {}

    def done(connection, result):
        try:
            connection.call_finish(result)
            outcome["ok"] = True
        except GLib.Error as err:
            outcome["error"] = err.message
        loop.quit()

    bus.call(
        bus.get_unique_name(), PATH, IFACE, "ClearPreviews", None, None,
        Gio.DBusCallFlags.NONE, 5000, None, done,
    )
    GLib.timeout_add(10000, loop.quit)
    loop.run()
    return outcome


def test_an_old_file_is_unpacked_read_only_and_the_current_one_is_untouched(bus, world):
    home, root = world

    _, finished, error = _preview(bus, str(home / "a.txt"))

    assert error is None and finished is not None and finished[1] is True, finished
    unpacked = finished[2]
    assert unpacked.startswith(str(root))
    assert open(unpacked).read() == "v1"
    assert not os.stat(unpacked).st_mode & stat.S_IWUSR
    assert (home / "a.txt").read_text() == "v2"


def test_a_whole_folder_is_unpacked(bus, world):
    home, _ = world

    _, finished, _ = _preview(bus, str(home / "proj"))

    assert finished is not None and finished[1] is True, finished
    assert open(os.path.join(finished[2], "sub", "n.txt")).read() == "old"
    assert (home / "proj" / "sub" / "n.txt").read_text() == "new"


def test_clearing_removes_every_preview(bus, world):
    home, root = world
    _preview(bus, str(home / "proj"))
    assert os.listdir(root)

    assert _clear(bus) == {"ok": True}

    assert os.listdir(root) == []


def test_a_path_outside_home_is_refused(bus, world):
    _, finished, error = _preview(bus, "/etc/passwd")

    assert finished is None and "InvalidPath" in error
