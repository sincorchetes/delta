import shutil

import pytest

from delta.application.repository_setup import RepositorySetup
from delta.domain.errors import EngineError, PassphraseError
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

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


@pytest.fixture
def world(tmp_path):
    store = MemoryStore()
    runner = BorgRunner(env={"BORG_BASE_DIR": str(tmp_path / "bh")}, secrets=store)
    return store, runner, Repository(str(tmp_path / "repo"))


def test_generated_passphrase_round_trips_through_keyring(world):
    store, runner, repo = world
    RepositorySetup(runner, store).create(repo)

    assert runner.list_snapshots(repo) == []


def test_missing_parent_directories_are_created_privately(tmp_path):
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "bh")})
    repo = Repository(str(tmp_path / "Backups" / "nested" / "repo"))

    runner.init(repo)

    parent = tmp_path / "Backups" / "nested"
    assert runner.list_snapshots(repo) == []
    assert (parent.stat().st_mode & 0o777) == 0o700


def test_unusable_parent_is_a_clear_error_not_a_crash(tmp_path):
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "bh")})
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")

    with pytest.raises(EngineError, match="cannot create"):
        runner.init(Repository(str(blocker / "repo")))


def test_ambient_borg_passphrase_never_overrides_the_keyring(world, monkeypatch):
    store, runner, repo = world
    RepositorySetup(runner, store).create(repo, "from the keyring")
    monkeypatch.setenv("BORG_PASSPHRASE", "leaked from the shell")
    monkeypatch.setenv("BORG_PASSCOMMAND", "echo leaked")

    assert runner.list_snapshots(repo) == []

    store.set(repo.location, "wrong")
    runner._forget_snapshots(repo)  # the list just read is remembered; ask borg again
    with pytest.raises(PassphraseError):
        runner.list_snapshots(repo)


def test_chosen_passphrase_is_used_by_borg(world):
    store, runner, repo = world
    RepositorySetup(runner, store).create(repo, "correct horse")
    store.set(repo.location, "wrong")

    with pytest.raises(PassphraseError):
        runner.list_snapshots(repo)

    store.set(repo.location, "correct horse")
    assert runner.list_snapshots(repo) == []
