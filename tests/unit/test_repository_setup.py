import pytest

from delta.application.repository_setup import RepositorySetup
from delta.domain.repository import Encryption, Repository


class FakeStore:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def get(self, key):
        return self.data.get(key)

    def set(self, key, secret):
        self.data[key] = secret

    def delete(self, key):
        self.data.pop(key, None)


class FakeEngine:
    def __init__(self, fail=False):
        self.fail = fail
        self.inited = []

    def init(self, repo):
        if self.fail:
            raise RuntimeError("init failed")
        self.inited.append(repo)


REPO = Repository("/backups/repo")


def test_chosen_passphrase_is_registered():
    store, engine = FakeStore(), FakeEngine()
    RepositorySetup(engine, store).create(REPO, "my-pass")
    assert store.data == {REPO.location: "my-pass"}
    assert engine.inited == [REPO]


def test_no_passphrase_generates_and_registers_a_strong_one():
    store = FakeStore()
    RepositorySetup(FakeEngine(), store).create(REPO)
    generated = store.data[REPO.location]
    assert len(generated) >= 43


def test_generated_passphrases_are_unique():
    first, second = FakeStore(), FakeStore()
    RepositorySetup(FakeEngine(), first).create(REPO)
    RepositorySetup(FakeEngine(), second).create(REPO)
    assert first.data != second.data


def test_failed_init_leaves_no_orphan_secret():
    store = FakeStore()
    with pytest.raises(RuntimeError):
        RepositorySetup(FakeEngine(fail=True), store).create(REPO, "x")
    assert store.data == {}


def test_failed_init_restores_previous_secret():
    store = FakeStore({REPO.location: "old"})
    with pytest.raises(RuntimeError):
        RepositorySetup(FakeEngine(fail=True), store).create(REPO, "new")
    assert store.data == {REPO.location: "old"}


def test_unencrypted_repository_is_refused():
    store, engine = FakeStore(), FakeEngine()
    with pytest.raises(ValueError):
        RepositorySetup(engine, store).create(Repository("/r", Encryption.NONE))
    assert store.data == {} and engine.inited == []


class OpeningEngine(FakeEngine):
    def __init__(self, opens=True):
        super().__init__()
        self.opens = opens
        self.listed = []

    def list_snapshots(self, repo):
        self.listed.append(repo)
        if not self.opens:
            raise RuntimeError("passphrase is incorrect")
        return []


def test_adopting_registers_the_passphrase_and_never_initialises():
    store, engine = FakeStore(), OpeningEngine()
    RepositorySetup(engine, store).adopt(REPO, "mine")
    assert store.data == {REPO.location: "mine"}
    assert engine.listed == [REPO] and engine.inited == []


def test_a_passphrase_that_does_not_open_the_repository_leaves_the_keyring_alone():
    store = FakeStore({REPO.location: "old"})
    with pytest.raises(RuntimeError):
        RepositorySetup(OpeningEngine(opens=False), store).adopt(REPO, "wrong")
    assert store.data == {REPO.location: "old"}


def test_a_failed_adoption_without_a_previous_secret_leaves_nothing():
    store = FakeStore()
    with pytest.raises(RuntimeError):
        RepositorySetup(OpeningEngine(opens=False), store).adopt(REPO, "wrong")
    assert store.data == {}


def test_adopting_needs_a_passphrase_and_encryption():
    store, engine = FakeStore(), OpeningEngine()
    with pytest.raises(ValueError):
        RepositorySetup(engine, store).adopt(REPO, "")
    with pytest.raises(ValueError):
        RepositorySetup(engine, store).adopt(Repository("/r", Encryption.NONE), "x")
    assert store.data == {} and engine.listed == []


def test_adopting_reports_when_the_newest_snapshot_was_made():
    from datetime import datetime, timezone

    from delta.domain.snapshot import Snapshot

    older = Snapshot("a", "a", datetime(2026, 1, 1, tzinfo=timezone.utc))
    newer = Snapshot("b", "b", datetime(2026, 3, 1, tzinfo=timezone.utc))

    class WithSnapshots(OpeningEngine):
        def list_snapshots(self, repo):
            return [older, newer]

    assert RepositorySetup(WithSnapshots(), FakeStore()).adopt(REPO, "x") == int(newer.created.timestamp())
    assert RepositorySetup(OpeningEngine(), FakeStore()).adopt(REPO, "x") == 0
