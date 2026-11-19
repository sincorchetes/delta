import shutil

import pytest
from dbus_helpers import call_and_wait_finished, call_rows
from gi.repository import GLib

from delta.application.deleted_service import DeletedService
from delta.application.restore_service import RestoreService
from delta.application.snapshot_service import SnapshotService
from delta.application.version_service import VersionService
from delta.daemon.job_runner import JobRunner
from delta.daemon.service import DeltaService
from delta.domain.backup_job import BackupJob
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


@pytest.fixture
def world(bus, tmp_path):
    home = tmp_path / "home"
    (home / "docs").mkdir(parents=True)
    (home / "trip" / "raw").mkdir(parents=True)
    (home / "docs" / "a.txt").write_text("alpha")
    (home / "docs" / "b.txt").write_text("beta")
    (home / "keep.txt").write_text("kept")
    (home / "trip" / "1.jpg").write_text("one")
    (home / "trip" / "raw" / "2.nef").write_text("two")
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "bh")})
    repo = Repository(str(tmp_path / "repo"))
    runner.init(repo)
    runner.create(repo, BackupJob("j", (str(home),)), "first")

    (home / "docs" / "a.txt").unlink()  # deleted
    shutil.rmtree(home / "trip")  # a whole folder, deleted
    (home / "docs" / "b.txt").write_text("changed afterwards")  # modified, not deleted

    restore = RestoreService(runner, repo, str(home))
    service = DeltaService(
        bus,
        SnapshotService(runner, repo),
        JobRunner(bus),
        restore=restore,
        versions=VersionService(runner, repo, str(home)),
        deleted=DeletedService(runner, repo, str(home), restore),
    )
    yield home
    service.unregister()


def _list(bus, folder, snapshot="first"):
    return call_rows(bus, "ListDeleted", GLib.Variant("(ss)", (snapshot, str(folder))))


def _restore(bus, folder, snapshot="first"):
    return call_and_wait_finished(bus, "RestoreDeleted", GLib.Variant("(ss)", (snapshot, str(folder))))


def test_what_is_gone_is_listed_with_a_deleted_folder_as_one_item(bus, world):
    rows = _list(bus, world)["rows"]

    items = {row["name"]: row for row in rows}
    assert set(items) == {"docs/a.txt", "trip"}
    assert items["trip"]["is_dir"] is True and items["trip"]["size"] == len("one") + len("two")
    assert items["docs/a.txt"]["size"] == len("alpha")


def test_what_exists_today_is_not_listed_even_if_it_changed(bus, world):
    names = {row["name"] for row in _list(bus, world)["rows"]}
    assert "docs/b.txt" not in names and "keep.txt" not in names


def test_everything_deleted_comes_back_under_its_own_name_in_one_job(bus, world):
    _, finished, error = _restore(bus, world)

    assert error is None and finished is not None and finished[1] is True, finished
    assert finished[2] == "2"  # items put back: the file and the whole folder
    assert (world / "docs" / "a.txt").read_text() == "alpha"
    assert (world / "trip" / "1.jpg").read_text() == "one"
    assert (world / "trip" / "raw" / "2.nef").read_text() == "two"


def test_what_exists_today_is_never_touched(bus, world):
    _restore(bus, world)
    assert (world / "docs" / "b.txt").read_text() == "changed afterwards"
    assert (world / "keep.txt").read_text() == "kept"


def test_after_restoring_nothing_is_left_to_restore(bus, world):
    _restore(bus, world)

    assert _list(bus, world)["rows"] == []
    _, finished, _ = _restore(bus, world)
    assert finished[2] == "0"


def test_no_scratch_folder_is_left_behind(bus, world):
    _restore(bus, world)
    assert [p.name for p in world.iterdir() if p.name.startswith(".delta-restore-")] == []


def test_a_folder_can_be_looked_at_on_its_own(bus, world):
    names = [row["name"] for row in _list(bus, world / "docs")["rows"]]
    assert names == ["a.txt"]


def test_an_unknown_snapshot_or_a_path_outside_home_is_refused(bus, world):
    assert "error" in _list(bus, world, snapshot="nope")
    assert "InvalidPath" in _list(bus, "/etc")["error"]
    _, finished, error = _restore(bus, "/etc")
    assert finished is None and "InvalidPath" in error


# --- what changed, not only what is gone ------------------------------------------------------


def _changed(bus, folder, snapshot="first"):
    return call_rows(bus, "ListChanged", GLib.Variant("(ss)", (snapshot, str(folder))))


def test_changes_are_the_deleted_plus_what_was_modified_in_name_order(bus, world):
    rows = _changed(bus, world)["rows"]

    assert [row["name"] for row in rows] == ["docs/a.txt", "docs/b.txt", "trip"]


def test_a_file_that_is_the_same_as_in_the_backup_is_not_a_change(bus, world):
    names = {row["name"] for row in _changed(bus, world)["rows"]}
    assert "keep.txt" not in names


def test_what_was_restored_stops_being_a_change_but_the_modified_file_remains(bus, world):
    _restore(bus, world)

    rows = _changed(bus, world)["rows"]

    assert [row["name"] for row in rows] == ["docs/b.txt"]


def test_changes_below_a_subfolder_are_named_relative_to_it(bus, world):
    assert [row["name"] for row in _changed(bus, world / "docs")["rows"]] == ["a.txt", "b.txt"]


def test_changes_are_refused_for_an_unknown_snapshot_or_outside_home(bus, world):
    assert "error" in _changed(bus, world, snapshot="nope")
    assert "InvalidPath" in _changed(bus, "/etc")["error"]
