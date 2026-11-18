"""What the restore and preview services do when the disk or the repository lets them down."""

import errno
import os
import tempfile
from datetime import datetime

import pytest

from delta.application import restore_service
from delta.application.preview_service import PreviewService
from delta.application.restore_service import RestoreService
from delta.domain.errors import DeltaError, InvalidPath
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot

NOW = datetime(2026, 11, 10, 13, 5, 0)
NO_SPACE = OSError(errno.ENOSPC, "No space left on device")


class Engine:
    def __init__(self, files=None, extract_error=None, links=None):
        self.files = files or {}
        self.links = links or {}
        self.extract_error = extract_error

    def list_snapshots(self, repo):
        return [Snapshot("id1", "first", NOW)]

    def extract(self, repo, snapshot, paths, destination):
        if self.extract_error:
            raise self.extract_error
        for path in paths:
            target = os.path.join(destination, path.lstrip("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if path in self.links:
                os.symlink(self.links[path], target)
            else:
                with open(target, "w") as handle:
                    handle.write(self.files.get(path, ""))


@pytest.fixture
def home(tmp_path):
    root = tmp_path / "home"
    (root / "docs").mkdir(parents=True)
    return root


def restorer(home, engine, repo: str | None = "/r"):
    return RestoreService(engine, Repository(repo) if repo else None, str(home), clock=lambda: NOW)


def fail_with(error):
    def raiser(*_args, **_kwargs):
        raise error

    return raiser


# --- restoring beside the original ---------------------------------------------------------------


def test_restoring_beside_without_a_repository_says_so(home):
    with pytest.raises(DeltaError, match="no repository"):
        restorer(home, Engine(), repo=None).restore_beside("first", str(home / "docs" / "a.txt"), replace=False)


def test_a_full_disk_while_preparing_the_scratch_folder_is_a_clear_error(home, monkeypatch):
    monkeypatch.setattr(tempfile, "mkdtemp", fail_with(NO_SPACE))

    with pytest.raises(DeltaError, match="cannot restore into"):
        restorer(home, Engine()).restore_beside("first", str(home / "docs" / "a.txt"), replace=False)


def test_a_folder_that_cannot_be_recreated_leaves_nothing_behind(home, monkeypatch):
    real_mkdir = os.mkdir
    calls = []

    def second_mkdir_fails(path, *args, **kwargs):
        calls.append(path)
        if len(calls) == 2:
            raise OSError(errno.EACCES, "Permission denied")
        real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(os, "mkdir", second_mkdir_fails)
    source = home / "docs" / "gone" / "deeper" / "a.txt"

    with pytest.raises(DeltaError, match="cannot recreate"):
        restorer(home, Engine(files={str(source): "old"})).restore_beside("first", str(source), replace=False)

    assert not (home / "docs" / "gone").exists()


def test_looking_for_a_folder_never_runs_past_the_top_of_the_tree(home):
    with pytest.raises(InvalidPath):
        restorer(home, Engine())._recreate_folder("no-such-folder")


def test_forgetting_never_removes_a_folder_that_has_content(tmp_path):
    full = tmp_path / "full"
    full.mkdir()
    (full / "keep.txt").write_text("keep")

    RestoreService._forget([str(full)])

    assert (full / "keep.txt").exists()


def test_files_that_cannot_be_compared_are_not_the_same(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_text("x")
    b.write_text("x")
    monkeypatch.setattr(restore_service, "_same_bytes", fail_with(OSError(errno.EIO, "I/O error")))

    assert restore_service._same_file(str(a), str(b)) is False


# --- putting back what was deleted ---------------------------------------------------------------


def test_putting_back_without_a_repository_says_so(home):
    with pytest.raises(DeltaError, match="no repository"):
        restorer(home, Engine(), repo=None).place_missing("first", [str(home / "docs" / "a.txt")])


def test_a_full_disk_while_preparing_to_put_back_is_a_clear_error(home, monkeypatch):
    monkeypatch.setattr(tempfile, "mkdtemp", fail_with(NO_SPACE))

    with pytest.raises(DeltaError, match="cannot restore"):
        restorer(home, Engine()).place_missing("first", [str(home / "docs" / "a.txt")])


def test_a_disk_error_while_putting_back_is_reported_and_the_scratch_folder_removed(home):
    engine = Engine(extract_error=OSError(errno.EIO, "I/O error"))

    with pytest.raises(DeltaError):
        restorer(home, engine).place_missing("first", [str(home / "docs" / "a.txt")])

    assert [name for name in os.listdir(home) if name.startswith(restore_service.SCRATCH_PREFIX)] == []


# --- previews ------------------------------------------------------------------------------------


def previewer(root, engine):
    return PreviewService(engine, Repository("/r"), "/home/u", str(root))


def test_a_link_in_a_preview_is_left_alone_when_making_it_read_only(tmp_path):
    engine = Engine(files={"/home/u/a.txt": "old"}, links={"/home/u/link": "a.txt"})
    root = tmp_path / "preview"

    previewer(root, engine).preview("first", "/home/u/link")

    assert any(os.path.islink(os.path.join(folder, name)) for folder, _d, names in os.walk(root) for name in names)


def test_a_preview_folder_that_cannot_be_made_is_a_clear_error(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where a folder should be")

    with pytest.raises(DeltaError, match="cannot prepare a preview"):
        previewer(blocker / "preview", Engine()).preview("first", "/home/u/a.txt")


def test_a_disk_error_while_unpacking_leaves_no_preview_behind(tmp_path):
    root = tmp_path / "preview"
    engine = Engine(extract_error=OSError(errno.EIO, "I/O error"))

    with pytest.raises(DeltaError):
        previewer(root, engine).preview("first", "/home/u/a.txt")

    assert os.listdir(root) == []
