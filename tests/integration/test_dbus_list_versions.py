import os
import shutil

import gi
import pytest

gi.require_version("Gio", "2.0")
from dbus_helpers import IFACE, PATH
from gi.repository import Gio, GLib

from delta.application.snapshot_service import SnapshotService
from delta.application.version_service import VersionService
from delta.daemon.service import DeltaService
from delta.domain.backup_job import BackupJob
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


def _list_versions(bus, path):
    return _rows(bus, "ListVersions", GLib.Variant("(s)", (path,)))


def _list_folder(bus, snapshot, path):
    return _rows(bus, "ListFolder", GLib.Variant("(ss)", (snapshot, path)))


def _search_folder(bus, snapshot, path, query):
    return _rows(bus, "SearchFolder", GLib.Variant("(sss)", (snapshot, path, query)))


def _rows(bus, method, parameters):
    loop = GLib.MainLoop()
    outcome = {}

    def done(connection, result):
        try:
            outcome["rows"] = connection.call_finish(result).unpack()[0]
        except GLib.Error as err:
            outcome["error"] = err.message
        loop.quit()

    bus.call(
        bus.get_unique_name(), PATH, IFACE, method, parameters, None,
        Gio.DBusCallFlags.NONE, 5000, None, done,
    )
    GLib.timeout_add(10000, loop.quit)
    loop.run()
    return outcome


@pytest.fixture
def world(bus, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    target = home / "a.txt"
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "bh")})
    repo = Repository(str(tmp_path / "repo"))
    runner.init(repo)
    job = BackupJob("j", (str(home),))
    target.write_text("one")
    os.utime(target, (1_700_000_000, 1_700_000_000))
    (home / "dir" / "deep").mkdir(parents=True)
    inner = home / "dir" / "deep" / "f.txt"
    inner.write_text("1")
    for path in (inner, inner.parent, inner.parent.parent):  # folders carry their own mtime too
        os.utime(path, (1_700_000_000, 1_700_000_000))
    runner.create(repo, job, "s1")
    runner.create(repo, job, "s2")
    target.write_text("changed!")
    os.utime(target, (1_700_000_500, 1_700_000_500))
    inner.write_text("22")
    os.utime(inner, (1_700_000_600, 1_700_000_600))
    runner.create(repo, job, "s3")
    service = DeltaService(
        bus,
        SnapshotService(runner, repo),
        versions=VersionService(runner, repo, str(home)),
    )
    yield home, target
    service.unregister()


def test_list_versions_collapses_identical_snapshots(bus, world):
    _, target = world
    outcome = _list_versions(bus, str(target))
    assert [row["name"] for row in outcome["rows"]] == ["s3", "s1"]
    assert outcome["rows"][0]["size"] == len("changed!")
    assert outcome["rows"][0]["mtime"] == 1_700_000_500
    assert outcome["rows"][0]["is_dir"] is False


def test_a_folder_has_a_version_per_change_anywhere_below_it(bus, world):
    home, _ = world
    rows = _list_versions(bus, str(home / "dir"))["rows"]
    assert [row["name"] for row in rows] == ["s3", "s1"]
    assert rows[0]["mtime"] == 1_700_000_600
    assert rows[0]["size"] == len("22") and rows[1]["size"] == len("1")
    assert all(row["is_dir"] is True for row in rows)


def test_a_folder_is_listed_as_it_was_in_one_snapshot(bus, world):
    home, _ = world

    old = {row["name"]: row for row in _list_folder(bus, "s1", str(home))["rows"]}
    new = {row["name"]: row for row in _list_folder(bus, "s3", str(home))["rows"]}

    assert set(old) == set(new) == {"a.txt", "dir"}
    assert old["a.txt"]["size"] == len("one") and new["a.txt"]["size"] == len("changed!")
    assert old["a.txt"]["is_dir"] is False and old["dir"]["is_dir"] is True
    assert old["dir"]["size"] == len("1") and new["dir"]["size"] == len("22")


def test_a_subfolder_is_listed_one_level_at_a_time(bus, world):
    home, _ = world
    rows = _list_folder(bus, "s3", str(home / "dir"))["rows"]
    assert [(row["name"], row["is_dir"]) for row in rows] == [("deep", True)]


def test_a_search_finds_what_is_deep_inside_with_a_path_relative_to_the_folder(bus, world):
    home, _ = world

    rows = _search_folder(bus, "s3", str(home), "F.TXT")["rows"]

    assert [(row["name"], row["is_dir"], row["size"]) for row in rows] == [("dir/deep/f.txt", False, len("22"))]


def test_a_search_can_match_a_folder(bus, world):
    home, _ = world
    rows = _search_folder(bus, "s1", str(home), "deep")["rows"]
    assert [(row["name"], row["is_dir"]) for row in rows] == [("dir/deep", True)]


def test_a_search_sees_a_snapshot_as_it_was(bus, world):
    home, _ = world
    old = _search_folder(bus, "s1", str(home), "f.txt")["rows"][0]
    new = _search_folder(bus, "s3", str(home), "f.txt")["rows"][0]
    assert old["size"] == len("1") and new["size"] == len("22")


def test_a_blank_search_finds_nothing(bus, world):
    home, _ = world
    assert _search_folder(bus, "s3", str(home), "   ")["rows"] == []


def test_searching_an_unknown_snapshot_or_outside_home_fails(bus, world):
    home, _ = world
    assert "error" in _search_folder(bus, "nope", str(home), "x")
    assert "InvalidPath" in _search_folder(bus, "s1", "/etc", "x")["error"]


def test_listing_a_folder_of_an_unknown_snapshot_fails(bus, world):
    home, _ = world
    assert "error" in _list_folder(bus, "nope", str(home))


def test_listing_a_folder_outside_home_is_refused(bus, world):
    assert "InvalidPath" in _list_folder(bus, "s1", "/etc")["error"]


def test_list_versions_of_untracked_path_is_empty(bus, world):
    home, _ = world
    assert _list_versions(bus, str(home / "never.txt"))["rows"] == []


def test_list_versions_rejects_path_outside_home(bus, world):
    assert "InvalidPath" in _list_versions(bus, "/etc/passwd")["error"]
