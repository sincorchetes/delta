"""With Borg for real: a drive that goes away is a destination that cannot be reached, and nothing is made in its place."""

import shutil

import pytest

from delta.application.backup_service import BackupService
from delta.domain.backup_job import BackupJob, JobState
from delta.domain.destination import DestinationState
from delta.domain.errors import RepositoryNotFound
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner
from delta.infrastructure.local_destination import LocalDestination

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


@pytest.fixture
def world(tmp_path):
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "borg-home")})
    drive = tmp_path / "drive"
    drive.mkdir()
    repo = Repository(str(drive / "delta"))
    runner.init(repo)
    source = tmp_path / "home"
    source.mkdir()
    (source / "notes.txt").write_text("keep")
    return runner, repo, drive, source


def run_backup(runner, repo, source, probe=True):
    backup = BackupService(runner, repo, (str(source),), destination=LocalDestination() if probe else None)
    job = backup.new_job()
    backup.run(job)
    return job


def test_the_repository_is_backed_up_while_the_drive_is_there(world):
    runner, repo, _drive, source = world

    assert run_backup(runner, repo, source).state is JobState.SUCCEEDED


def test_a_drive_that_went_away_makes_the_backup_wait_and_nothing_is_created_where_it_was(world):
    runner, repo, drive, source = world
    shutil.rmtree(drive)  # the drive is unplugged

    job = run_backup(runner, repo, source)

    assert job.state is JobState.UNAVAILABLE
    assert job.unavailable.state is DestinationState.MISSING and job.unavailable.location == repo.location
    assert not drive.exists()  # not a folder made on the disk of the computer to hold the copy


def test_the_mount_point_of_a_drive_that_is_not_mounted_is_not_a_place_for_the_copy_either(world):
    # The repository is the root of the drive: unmounted, what stays on the computer is an empty folder.
    runner, _repo, drive, source = world
    shutil.rmtree(drive)
    drive.mkdir()

    job = run_backup(runner, Repository(str(drive)), source)

    assert job.state is JobState.UNAVAILABLE and job.unavailable.state is DestinationState.EMPTY
    assert list(drive.iterdir()) == []


def test_a_repository_in_a_folder_of_a_drive_that_is_not_mounted_is_a_folder_that_is_not_there(world):
    runner, repo, drive, source = world
    shutil.rmtree(drive)
    drive.mkdir()

    job = run_backup(runner, repo, source)

    assert job.state is JobState.UNAVAILABLE and job.unavailable.state is DestinationState.MISSING
    assert list(drive.iterdir()) == []


def test_borg_alone_does_not_make_a_repository_where_there_is_none(world):
    # What the claim "nothing is written to the disk of the computer" rests on: the engine refuses by itself too.
    runner, repo, drive, source = world
    shutil.rmtree(drive)

    with pytest.raises(RepositoryNotFound):
        runner.create(repo, BackupJob("j", (str(source),)), "snap")

    assert not drive.exists()


def test_another_disk_at_the_mount_point_does_not_have_the_folder_of_the_repository(world):
    # The repository is a folder inside the drive: on somebody else's disk that folder is not there, which is what is said.
    runner, repo, drive, source = world
    shutil.rmtree(drive)
    drive.mkdir()
    (drive / "holiday.jpg").write_text("somebody else's disk")

    job = run_backup(runner, repo, source)

    assert job.state is JobState.UNAVAILABLE and job.unavailable.state is DestinationState.MISSING
    assert sorted(path.name for path in drive.iterdir()) == ["holiday.jpg"]


def test_a_folder_that_is_there_and_holds_no_repository_is_a_repository_not_found_and_is_left_alone(world):
    # With the repository at the root of the drive, somebody else's disk there is a folder with something in it: the
    # destination can be reached, and what it holds is not a repository. That is the error that has its own name.
    runner, _repo, drive, source = world
    shutil.rmtree(drive)
    drive.mkdir()
    (drive / "holiday.jpg").write_text("somebody else's disk")
    at_the_root = Repository(str(drive))

    job = run_backup(runner, at_the_root, source)

    assert job.state is JobState.FAILED and job.unavailable is None
    assert sorted(path.name for path in drive.iterdir()) == ["holiday.jpg"]


def test_the_engine_names_that_case_repository_not_found(world):
    runner, _repo, drive, source = world
    shutil.rmtree(drive)
    drive.mkdir()
    (drive / "holiday.jpg").write_text("somebody else's disk")

    with pytest.raises(RepositoryNotFound):
        runner.create(Repository(str(drive)), BackupJob("j", (str(source),)), "snap")
