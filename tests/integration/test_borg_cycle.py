import shutil

import pytest

from delta.domain.backup_job import BackupJob
from delta.domain.errors import PassphraseError, RepositoryNotFound
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")

ENV = {"BORG_PASSPHRASE": "s3cret", "BORG_BASE_DIR": ""}


@pytest.fixture
def runner(tmp_path):
    return BorgRunner(env={**ENV, "BORG_BASE_DIR": str(tmp_path / "borg-home")})


@pytest.fixture
def repo(tmp_path, runner):
    repository = Repository(str(tmp_path / "repo"))
    runner.init(repository)
    return repository


@pytest.fixture
def data(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.txt").write_text("v1")
    return root


def test_full_cycle(tmp_path, runner, repo, data):
    job = BackupJob("j", (str(data),))
    first = runner.create(repo, job, "first")
    (data / "a.txt").write_text("v2")
    runner.create(repo, job, "second")

    snapshots = runner.list_snapshots(repo)
    assert [s.name for s in snapshots] == [first, "second"]

    dest = tmp_path / "restore"
    dest.mkdir()
    runner.extract(repo, "first", (str(data / "a.txt"),), str(dest))
    assert (dest / str(data).lstrip("/") / "a.txt").read_text() == "v1"

    runner.prune(repo, RetentionPolicy(1, 0, 0, 0))
    assert len(runner.list_snapshots(repo)) == 1


def test_create_with_progress_callback(runner, repo, data):
    events = []
    runner.create(repo, BackupJob("j", (str(data),)), "streamed", on_progress=events.append)
    assert [s.name for s in runner.list_snapshots(repo)] == ["streamed"]
    assert all(e.files >= 0 for e in events)


def test_streaming_create_maps_errors(tmp_path, runner, data):
    missing = Repository(str(tmp_path / "nope"))
    with pytest.raises(RepositoryNotFound):
        runner.create(missing, BackupJob("j", (str(data),)), "x", on_progress=lambda e: None)


def test_missing_repository(tmp_path, runner):
    with pytest.raises(RepositoryNotFound):
        runner.list_snapshots(Repository(str(tmp_path / "nope")))


def test_wrong_passphrase(tmp_path, repo):
    wrong = BorgRunner(env={"BORG_PASSPHRASE": "bad", "BORG_BASE_DIR": str(tmp_path / "other")})
    with pytest.raises(PassphraseError):
        wrong.list_snapshots(repo)
