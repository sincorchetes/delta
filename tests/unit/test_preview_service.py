import os
import stat
from datetime import datetime

import pytest

from delta.application.preview_service import PreviewService
from delta.domain.errors import DeltaError, InvalidPath, SnapshotNotFound
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot

NOW = datetime(2026, 11, 12, 10, 0, 0)


class FakeEngine:
    def __init__(self, files=None, folders=None):
        self.files = files or {}
        self.folders = folders or {}

    def list_snapshots(self, repo):
        return [Snapshot("id1", "first", NOW)]

    def extract(self, repo, snapshot, paths, destination):
        for path in paths:
            target = os.path.join(destination, path.lstrip("/"))
            for name, content in {".": self.files.get(path), **self.folders.get(path, {})}.items():
                if content is None:
                    continue
                where = target if name == "." else os.path.join(target, name)
                os.makedirs(os.path.dirname(where), exist_ok=True)
                with open(where, "w") as handle:
                    handle.write(content)


@pytest.fixture
def root(tmp_path):
    return tmp_path / "run" / "preview"


def service(root, engine, repo=Repository("/r")):
    return PreviewService(engine, repo, "/home/u", str(root))


def read(path):
    with open(path) as handle:
        return handle.read()


def test_a_file_is_unpacked_under_the_preview_folder_keeping_its_name(root):
    unpacked = service(root, FakeEngine(files={"/home/u/a.txt": "old"})).preview("first", "/home/u/a.txt")

    assert unpacked.startswith(str(root)) and os.path.basename(unpacked) == "a.txt"
    assert read(unpacked) == "old"


def test_a_snapshot_can_be_named_by_its_id(root):
    unpacked = service(root, FakeEngine(files={"/home/u/a.txt": "old"})).preview("id1", "/home/u/a.txt")
    assert read(unpacked) == "old"


def test_a_folder_is_unpacked_whole(root):
    engine = FakeEngine(folders={"/home/u/proj": {"sub/n.txt": "deep", "m.txt": "top"}})

    unpacked = service(root, engine).preview("first", "/home/u/proj")

    assert read(os.path.join(unpacked, "sub", "n.txt")) == "deep"
    assert read(os.path.join(unpacked, "m.txt")) == "top"


def test_nothing_in_a_preview_is_writable(root):
    engine = FakeEngine(folders={"/home/u/proj": {"sub/n.txt": "deep"}})

    unpacked = service(root, engine).preview("first", "/home/u/proj")

    for folder, _, files in os.walk(unpacked):
        for path in [folder, *(os.path.join(folder, name) for name in files)]:
            assert not os.stat(path).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH), path


def test_clear_removes_read_only_previews(root):
    previews = service(root, FakeEngine(folders={"/home/u/proj": {"sub/n.txt": "deep"}}))
    previews.preview("first", "/home/u/proj")
    previews.preview("first", "/home/u/proj")

    previews.clear()

    assert os.listdir(root) == []


def test_clear_without_any_preview_is_harmless(root):
    service(root, FakeEngine()).clear()


def test_two_previews_of_the_same_version_do_not_collide(root):
    previews = service(root, FakeEngine(files={"/home/u/a.txt": "old"}))
    first = previews.preview("first", "/home/u/a.txt")
    second = previews.preview("first", "/home/u/a.txt")

    assert first != second


def test_a_path_the_snapshot_lacks_leaves_nothing_behind(root):
    with pytest.raises(SnapshotNotFound):
        service(root, FakeEngine()).preview("first", "/home/u/missing.txt")
    assert os.listdir(root) == []


def test_an_unknown_snapshot_is_refused(root):
    with pytest.raises(SnapshotNotFound):
        service(root, FakeEngine(files={"/home/u/a.txt": "x"})).preview("nope", "/home/u/a.txt")


def test_without_a_repository_it_says_so(root):
    with pytest.raises(DeltaError):
        service(root, FakeEngine(), repo=None).preview("first", "/home/u/a.txt")


def test_only_paths_inside_home_can_be_previewed(root):
    previews = service(root, FakeEngine())
    assert previews.prepare("/home/u/docs/a.txt") == "/home/u/docs/a.txt"
    for outside in ("/etc/passwd", "/home/u/../other/a", "relative.txt"):
        with pytest.raises(InvalidPath):
            previews.prepare(outside)
