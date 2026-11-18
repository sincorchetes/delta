"""What a mutation run showed nothing watched in what the services hand to the engine and the disk."""

import os
import stat
from datetime import datetime

import pytest

from delta.application.backup_service import BackupService
from delta.application.deleted_service import DeletedService
from delta.application.preview_service import PreviewService
from delta.application.prune_service import PruneService
from delta.application.repository_setup import generate_passphrase
from delta.application.restore_service import SCRATCH_PREFIX, RestoreService
from delta.application.snapshot_service import SnapshotService
from delta.application.snapshots import snapshot_name
from delta.application.version_service import VersionService
from delta.domain.backup_job import BackupJob
from delta.domain.errors import InvalidPath
from delta.domain.file_version import FileEntry
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy
from delta.domain.snapshot import Snapshot

REPO = Repository("/srv/repo")
WHEN = datetime(2026, 1, 2, 3, 4, 5)


# --- secrets and permissions -------------------------------------------------------------------------


def test_a_generated_passphrase_carries_thirty_two_bytes_of_randomness():
    first, second = generate_passphrase(), generate_passphrase()

    assert len(first) == 43  # 32 bytes, URL-safe base64 without padding
    assert first != second


def test_the_preview_folder_is_private_to_the_user(tmp_path):
    class Engine:
        def list_snapshots(self, repo):
            return [Snapshot("id1", "first", WHEN)]

        def extract(self, repo, snapshot, paths, destination):
            target = os.path.join(destination, paths[0].lstrip("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            open(target, "w").close()

    root = tmp_path / "run" / "preview"
    previews = PreviewService(Engine(), REPO, "/home/u", str(root))

    previews.preview("first", "/home/u/a.txt")

    assert stat.S_IMODE(os.stat(root).st_mode) == 0o700


# --- the right repository reaches the engine ---------------------------------------------------------


class Spy:
    """Stands in for the engine and insists on being given the repository the service was built with."""

    def __init__(self):
        self.calls, self.destinations = [], []

    def _seen(self, name, repo, snapshot="first"):
        self.calls.append(name)
        assert repo is REPO, f"{name} was not given the repository"
        assert snapshot == "first", f"{name} was not given the snapshot's name"

    def list_snapshots(self, repo):
        self._seen("list_snapshots", repo)
        return [Snapshot("id1", "first", WHEN)]

    def file_entry(self, repo, snapshot, path):
        self._seen("file_entry", repo, snapshot)
        assert path.endswith("/docs/a.txt")
        return FileEntry(1, WHEN)

    def list_folder(self, repo, snapshot, path):
        self._seen("list_folder", repo, snapshot)
        assert path.startswith("/")
        return []

    def search_folder(self, repo, snapshot, path, query, limit):
        self._seen("search_folder", repo, snapshot)
        assert path.startswith("/") and query == "a" and limit > 0
        return []

    def list_tree(self, repo, snapshot, path):
        self._seen("list_tree", repo, snapshot)
        assert path.startswith("/")
        return []

    def extract(self, repo, snapshot, paths, destination):
        self._seen("extract", repo, snapshot)
        assert isinstance(paths, tuple) and paths and all(isinstance(p, str) for p in paths)
        assert isinstance(destination, str)
        self.destinations.append(destination)
        target = os.path.join(destination, paths[0].lstrip("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        open(target, "w").close()

    def prune(self, repo, policy):
        self._seen("prune", repo)
        assert isinstance(policy, RetentionPolicy)

    def create(self, repo, job, name=None, on_progress=None):
        self._seen("create", repo)
        assert isinstance(job, BackupJob)


def test_every_service_hands_its_repository_to_the_engine(tmp_path):
    spy = Spy()
    home = str(tmp_path / "home")
    os.makedirs(home + "/docs")

    assert [s.name for s in SnapshotService(spy, REPO).list_snapshots()] == ["first"]
    assert snapshot_name(spy, REPO, "first") == "first"
    versions = VersionService(spy, REPO, home)
    assert len(versions.list_versions(home + "/docs/a.txt")) == 1
    versions.list_folder("first", home + "/docs")
    versions.search_folder("first", home + "/docs", "a")
    restore = RestoreService(spy, REPO, home)
    restore.restore_beside("first", home + "/docs/a.txt", replace=False)
    restore.place_missing("first", [home + "/docs/b.txt"])
    restore.restore("first", home + "/docs/c.txt", home + "/docs")
    DeletedService(spy, REPO, home, restore).find("first", home + "/docs")
    PreviewService(spy, REPO, home, str(tmp_path / "preview")).preview("first", home + "/docs/a.txt")
    PruneService(spy, REPO, RetentionPolicy()).run()
    backup = BackupService(spy, REPO, (home,))
    backup.run(backup.new_job())

    assert {"list_snapshots", "file_entry", "list_folder", "search_folder", "list_tree", "extract", "prune", "create"} <= set(spy.calls)


def test_what_is_unpacked_waits_in_a_hidden_folder_next_to_where_it_will_go(tmp_path):
    spy, home = Spy(), tmp_path / "home"
    (home / "docs").mkdir(parents=True)
    restore = RestoreService(spy, REPO, str(home))

    restore.restore_beside("first", str(home / "docs" / "a.txt"), replace=False)
    restore.place_missing("first", [str(home / "docs" / "b.txt")])

    beside, missing = spy.destinations
    assert os.path.dirname(beside) == os.path.realpath(home / "docs")
    assert os.path.dirname(missing) == os.path.realpath(home)
    assert all(os.path.basename(d).startswith(SCRATCH_PREFIX) for d in spy.destinations)


class FolderEngine:
    """Unpacks a folder holding one file."""

    def list_snapshots(self, repo):
        return [Snapshot("id1", "first", WHEN)]

    def extract(self, repo, snapshot, paths, destination):
        target = os.path.join(destination, paths[0].lstrip("/"))
        os.makedirs(target)
        open(os.path.join(target, "inside.txt"), "w").write("old")


def test_a_folder_with_a_dot_in_its_name_is_set_aside_whole_not_split_like_a_file(tmp_path):
    home = tmp_path / "home"
    (home / "docs" / "v1.2").mkdir(parents=True)
    (home / "docs" / "v1.2" / "inside.txt").write_text("now")
    service = RestoreService(FolderEngine(), REPO, str(home), clock=lambda: datetime(2026, 11, 10, 13, 5, 0))

    service.restore_beside("first", str(home / "docs" / "v1.2"), replace=True)

    assert sorted(os.listdir(home / "docs")) == ["v1.2", "v1.2 (before restore 2026-11-10 13-05-00)"]


def test_the_service_names_what_leaves_the_home_folder_once_symlinks_are_resolved(tmp_path):
    def resolve(path):
        return path if path == "/home/u" else "/tmp/elsewhere"

    service = RestoreService(Spy(), REPO, "/home/u", resolve=resolve)

    with pytest.raises(InvalidPath, match="target must be inside /home/u"):
        service.prepare("/home/u/a", "/home/u/link")
    with pytest.raises(InvalidPath, match="path must be inside /home/u"):
        service.prepare_in_place("/home/u/link/a.txt")


def test_a_deleted_folder_is_never_recreated_outside_home(tmp_path):
    (tmp_path / "home").mkdir()
    (tmp_path / "outside").mkdir()
    service = RestoreService(Spy(), REPO, str(tmp_path / "home"))

    with pytest.raises(InvalidPath, match="path must be inside"):
        service.restore_beside("first", str(tmp_path / "outside" / "gone" / "a.txt"), replace=False)
    assert not (tmp_path / "outside" / "gone").exists()


@pytest.mark.parametrize("repo", [None])
def test_without_a_repository_the_engine_is_never_asked(repo, tmp_path):
    spy = Spy()

    assert SnapshotService(spy, repo).list_snapshots() == []
    assert VersionService(spy, repo, "/home/u").list_versions("/home/u/a") == []
    assert PruneService(spy, repo, RetentionPolicy()).run() is False
    assert spy.calls == []
