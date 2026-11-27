import shutil

import pytest
from dbus_helpers import call_and_wait_finished

from delta.application.backup_notifications import BackupNotifications
from delta.application.repository_setup import RepositorySetup
from delta.application.snapshot_service import SnapshotService
from delta.daemon.job_runner import JobRunner
from delta.daemon.service import DeltaService
from delta.domain.backup_job import BackupJob
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner
from gi.repository import GLib

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
def world(bus, tmp_path):
    store = MemoryStore()
    runner = BorgRunner(env={"BORG_BASE_DIR": str(tmp_path / "bh")}, secrets=store)
    repo = Repository(str(tmp_path / "repo"))
    service = DeltaService(
        bus,
        SnapshotService(runner, repo),
        JobRunner(bus),
        setup=RepositorySetup(runner, store),
    )
    yield store, runner, repo
    service.unregister()


def test_empty_passphrase_generates_one_and_creates_encrypted_repo(bus, world):
    store, runner, repo = world

    _, finished, error = call_and_wait_finished(
        bus, "CreateRepository", GLib.Variant("(ss)", (repo.location, ""))
    )

    assert error is None and finished is not None and finished[1] is True, finished
    assert len(store.data[repo.location]) >= 43
    assert runner.list_snapshots(repo) == []


def test_chosen_passphrase_is_registered(bus, world):
    store, runner, repo = world

    _, finished, _ = call_and_wait_finished(
        bus, "CreateRepository", GLib.Variant("(ss)", (repo.location, "my passphrase"))
    )

    assert finished is not None and finished[1] is True, finished
    assert store.data[repo.location] == "my passphrase"
    assert runner.list_snapshots(repo) == []


def test_successful_creation_notifies_for_persisting_the_location(bus, tmp_path):
    store = MemoryStore()
    runner = BorgRunner(env={"BORG_BASE_DIR": str(tmp_path / "bh")}, secrets=store)
    repo = Repository(str(tmp_path / "repo"))
    saved = []
    service = DeltaService(
        bus,
        SnapshotService(runner, repo),
        JobRunner(bus),
        setup=RepositorySetup(runner, store),
        on_repository_created=saved.append,
    )

    _, finished, _ = call_and_wait_finished(
        bus, "CreateRepository", GLib.Variant("(ss)", (repo.location, ""))
    )
    GLib.MainContext.default().iteration(False)
    service.unregister()

    assert finished is not None and finished[1] is True, finished
    assert saved == [repo]


def test_failed_creation_notifies_the_user(bus, tmp_path):
    class Recorder:
        def __init__(self):
            self.sent = []

        def notify(self, notification):
            self.sent.append(notification)

    store, recorder = MemoryStore(), Recorder()
    runner = BorgRunner(env={"BORG_BASE_DIR": str(tmp_path / "bh")}, secrets=store)
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    service = DeltaService(
        bus,
        SnapshotService(runner, Repository(str(tmp_path / "unused"))),
        JobRunner(bus),
        setup=RepositorySetup(runner, store),
        notifications=BackupNotifications(recorder),
    )

    _, finished, _ = call_and_wait_finished(
        bus, "CreateRepository", GLib.Variant("(ss)", (str(blocker / "repo"), ""))
    )
    service.unregister()

    assert finished is not None and finished[1] is False
    assert [n.kind.value for n in recorder.sent] == ["repository-failed"]
    assert "cannot create" in recorder.sent[0].detail


def test_empty_location_is_invalid_argument(bus, world):
    _, finished, error = call_and_wait_finished(
        bus, "CreateRepository", GLib.Variant("(ss)", ("", ""))
    )

    assert finished is None
    assert error is not None and "InvalidArgument" in error


def test_failed_init_reports_error_and_leaves_no_secret(bus, world, tmp_path):
    store, _, _ = world
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    location = str(blocker / "repo")

    _, finished, _ = call_and_wait_finished(
        bus, "CreateRepository", GLib.Variant("(ss)", (location, ""))
    )

    assert finished is not None and finished[1] is False and finished[2]
    assert location not in store.data


def _created(bus, world, passphrase):
    store, runner, repo = world
    _, finished, _ = call_and_wait_finished(
        bus, "CreateRepository", GLib.Variant("(ss)", (repo.location, passphrase))
    )
    assert finished is not None and finished[1] is True, finished
    return store, runner, repo


def test_creating_over_an_existing_repository_is_refused_and_says_so(bus, world):
    _created(bus, world, "first")
    _, _, repo = world

    _, finished, _ = call_and_wait_finished(
        bus, "CreateRepository", GLib.Variant("(ss)", (repo.location, "second"))
    )

    assert finished is not None and finished[1] is False
    assert "repository already exists" in finished[2].lower()


def test_an_existing_repository_is_adopted_with_its_passphrase(bus, world):
    store, runner, repo = _created(bus, world, "right one")
    store.data.clear()  # a fresh keyring, as after reinstalling

    _, finished, _ = call_and_wait_finished(
        bus, "UseRepository", GLib.Variant("(ss)", (repo.location, "right one"))
    )

    assert finished is not None and finished[1] is True, finished
    assert store.data == {repo.location: "right one"}
    assert runner.list_snapshots(repo) == []


def test_a_wrong_passphrase_is_reported_and_not_kept(bus, world):
    store, _, repo = _created(bus, world, "right one")
    store.data.clear()

    _, finished, _ = call_and_wait_finished(
        bus, "UseRepository", GLib.Variant("(ss)", (repo.location, "wrong"))
    )

    assert finished is not None and finished[1] is False and finished[2]
    assert store.data == {}


def test_using_a_repository_needs_a_passphrase(bus, world):
    _, _, repo = world

    _, finished, error = call_and_wait_finished(
        bus, "UseRepository", GLib.Variant("(ss)", (repo.location, ""))
    )

    assert finished is None
    assert error is not None and "InvalidArgument" in error


def test_adopting_a_repository_makes_its_last_backup_known(bus, tmp_path):
    store = MemoryStore()
    runner = BorgRunner(env={"BORG_BASE_DIR": str(tmp_path / "bh")}, secrets=store)
    repo = Repository(str(tmp_path / "repo"))
    jobs = JobRunner(bus)
    service = DeltaService(
        bus, SnapshotService(runner, repo), jobs, setup=RepositorySetup(runner, store)
    )
    store.data[repo.location] = "pw"
    runner.init(repo)
    source = tmp_path / "data"
    source.mkdir()
    (source / "f").write_text("x")
    runner.create(repo, BackupJob(id="seed", sources=(str(source),)))
    store.data.clear()

    _, finished, _ = call_and_wait_finished(
        bus, "UseRepository", GLib.Variant("(ss)", (repo.location, "pw"))
    )
    service.unregister()

    assert finished is not None and finished[1] is True, finished
    assert jobs.last_backup > 0


def adoptable(bus, tmp_path, failure):
    """A repository with its passphrase gone from the keyring, after a backup that failed for it."""
    store = MemoryStore()
    runner = BorgRunner(env={"BORG_BASE_DIR": str(tmp_path / "bh")}, secrets=store)
    repo = Repository(str(tmp_path / "repo"))
    jobs = JobRunner(bus)
    service = DeltaService(bus, SnapshotService(runner, repo), jobs, setup=RepositorySetup(runner, store))
    store.data[repo.location] = "pw"
    runner.init(repo)
    store.data.clear()
    jobs.last_error = failure
    return repo, jobs, service


def test_adopting_a_repository_clears_the_error_that_asked_for_its_passphrase(bus, tmp_path):
    repo, jobs, service = adoptable(bus, tmp_path, "The passphrase for this repository is not in the keyring.")

    _, finished, _ = call_and_wait_finished(bus, "UseRepository", GLib.Variant("(ss)", (repo.location, "pw")))
    service.unregister()

    assert finished is not None and finished[1] is True, finished
    assert jobs.last_error == ""


def test_a_passphrase_that_does_not_open_the_repository_leaves_the_error_as_it_was(bus, tmp_path):
    repo, jobs, service = adoptable(bus, tmp_path, "The passphrase for this repository is not in the keyring.")

    _, finished, _ = call_and_wait_finished(bus, "UseRepository", GLib.Variant("(ss)", (repo.location, "wrong")))
    service.unregister()

    assert finished is not None and finished[1] is False, finished
    assert jobs.last_error == "The passphrase for this repository is not in the keyring."


def test_creating_a_repository_clears_the_error_of_the_last_backup(bus, tmp_path):
    store = MemoryStore()
    runner = BorgRunner(env={"BORG_BASE_DIR": str(tmp_path / "bh")}, secrets=store)
    repo = Repository(str(tmp_path / "new"))
    jobs = JobRunner(bus)
    service = DeltaService(bus, SnapshotService(runner, repo), jobs, setup=RepositorySetup(runner, store))
    jobs.last_error = "The passphrase for this repository is not in the keyring."

    _, finished, _ = call_and_wait_finished(bus, "CreateRepository", GLib.Variant("(ss)", (repo.location, "")))
    service.unregister()

    assert finished is not None and finished[1] is True, finished
    assert jobs.last_error == ""
