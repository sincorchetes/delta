import pytest

from delta.domain.backup_job import BackupJob, JobState
from delta.domain.repository import Encryption, Repository
from delta.domain.retention import RetentionPolicy


def test_repository_defaults_to_encrypted():
    assert Repository("/tmp/r").encryption is Encryption.REPOKEY_BLAKE2


def test_repository_rejects_empty_location():
    with pytest.raises(ValueError):
        Repository("")


@pytest.mark.parametrize("location", ["repo", "../repo", "~/backups", "me@nas.local:/b"])
def test_repository_must_be_an_absolute_path(location):
    with pytest.raises(ValueError):
        Repository(location)


@pytest.mark.parametrize("location", ["/srv/repo", "/run/media/ana/Disk/delta-backups", "/tmp/a:b"])
def test_repository_accepts_local_paths(location):
    assert Repository(location).location == location


def test_retention_defaults_are_gfs():
    assert RetentionPolicy().as_dict() == {
        "keep_hourly": 24,
        "keep_daily": 7,
        "keep_weekly": 4,
        "keep_monthly": 12,
    }


def test_retention_rejects_negative():
    with pytest.raises(ValueError):
        RetentionPolicy(keep_daily=-1)


def test_retention_keeps_anything():
    assert RetentionPolicy().keeps_anything
    assert not RetentionPolicy(0, 0, 0, 0).keeps_anything


def test_job_needs_sources():
    with pytest.raises(ValueError):
        BackupJob("j", ())


def test_job_happy_path():
    job = BackupJob("j", ("/home",))
    job.start()
    job.succeed()
    assert job.state is JobState.SUCCEEDED


def test_job_failure_records_message():
    job = BackupJob("j", ("/home",))
    job.start()
    job.fail("disk full")
    assert (job.state, job.message) == (JobState.FAILED, "disk full")


def test_job_rejects_invalid_transition():
    job = BackupJob("j", ("/home",))
    with pytest.raises(ValueError):
        job.succeed()
    job.start()
    job.succeed()
    with pytest.raises(ValueError):
        job.start()
