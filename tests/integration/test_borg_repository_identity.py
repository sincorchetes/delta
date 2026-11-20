"""With Borg for real: another repository in the place of the one Delta made is noticed, and nothing is written in it."""

import re
import shutil

import pytest

from delta.application.backup_service import BackupService
from delta.domain.backup_job import BackupJob, JobState
from delta.domain.destination import DestinationState
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


class Identity:
    def __init__(self):
        self.value = ""

    def expected(self):
        return self.value

    def remember(self, repo_id):
        self.value = repo_id


def runner_with(tmp_path, passphrase="x"):
    return BorgRunner(env={"BORG_PASSPHRASE": passphrase, "BORG_BASE_DIR": str(tmp_path / "borg-home")})


@pytest.fixture
def world(tmp_path):
    runner = runner_with(tmp_path)
    repo = Repository(str(tmp_path / "drive" / "delta"))
    repo_dir = tmp_path / "drive"
    repo_dir.mkdir()
    runner.init(repo)
    source = tmp_path / "home"
    source.mkdir()
    (source / "notes.txt").write_text("keep")
    identity = Identity()
    backup = BackupService(runner, repo, (str(source),), identity=identity)
    return runner, repo, source, backup, identity, tmp_path


def run(backup):
    job = backup.new_job()
    backup.run(job)
    return job


def replace_with_another_repository(repo, passphrase_runner):
    shutil.rmtree(repo.location)
    passphrase_runner.init(repo)


def test_the_identifier_is_what_borg_gave_the_repository_and_does_not_change(world):
    runner, repo, source, _backup, _identity, tmp_path = world

    first = runner.repository_id(repo)
    runner.create(repo, BackupJob("j", (str(source),)), "snap")

    assert re.fullmatch(r"[0-9a-f]{64}", first) and runner.repository_id(repo) == first
    other = Repository(str(tmp_path / "another"))
    runner.init(other)
    assert runner.repository_id(other) != first


def test_the_first_backup_learns_the_repository_and_the_next_ones_go_on(world):
    runner, repo, _source, backup, identity, _tmp = world

    assert run(backup).state is JobState.SUCCEEDED
    learnt = identity.value

    assert learnt == runner.repository_id(repo)
    assert run(backup).state is JobState.SUCCEEDED and identity.value == learnt


def test_another_repository_with_the_same_passphrase_is_noticed_and_nothing_is_written_in_it(world):
    runner, repo, _source, backup, identity, _tmp = world
    assert run(backup).state is JobState.SUCCEEDED
    mine = identity.value

    replace_with_another_repository(repo, runner)  # same passphrase: Borg opens it without a question

    job = run(backup)

    assert job.state is JobState.UNAVAILABLE and job.unavailable.state is DestinationState.OTHER_REPOSITORY
    assert runner.list_snapshots(repo) == []  # it was not written in
    assert identity.value == mine


def test_another_repository_with_another_passphrase_is_a_failure_and_is_not_written_in_either(world):
    runner, repo, _source, backup, identity, tmp_path = world
    assert run(backup).state is JobState.SUCCEEDED

    replace_with_another_repository(repo, runner_with(tmp_path, "another passphrase"))
    job = run(backup)

    assert job.state is JobState.FAILED
    assert runner_with(tmp_path, "another passphrase").list_snapshots(repo) == []


def test_an_older_copy_of_the_same_repository_is_not_written_in_either(world):
    runner, repo, source, backup, _identity, tmp_path = world
    assert run(backup).state is JobState.SUCCEEDED
    older = tmp_path / "older"
    shutil.copytree(repo.location, older)
    (source / "notes.txt").write_text("more")
    assert run(backup).state is JobState.SUCCEEDED  # the real repository is now ahead of the copy

    shutil.rmtree(repo.location)
    shutil.copytree(older, repo.location)  # the old disk, back in the same place
    job = run(backup)

    assert job.state is not JobState.SUCCEEDED
    assert len(runner.list_snapshots(repo)) in (0, 1)  # whatever it says, nothing was added to the old copy
