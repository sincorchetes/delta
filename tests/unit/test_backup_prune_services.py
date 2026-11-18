import pytest

from delta.application.backup_service import BackupService
from delta.application.prune_service import PruneService
from delta.domain.backup_job import JobState
from delta.domain.errors import RepositoryLocked
from delta.domain.progress import ProgressEvent
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy

REPO = Repository("/r")


class FakeEngine:
    def __init__(self, error=None):
        self.error = error
        self.pruned = []

    def create(self, repo, job, name=None, on_progress=None):
        if self.error:
            raise self.error
        if on_progress:
            on_progress(ProgressEvent(1, 10, "/a"))
        return "archive"

    def prune(self, repo, policy):
        self.pruned.append(policy)


def test_successful_backup_reports_progress():
    events = []
    service = BackupService(FakeEngine(), REPO, ("/home",))
    job = service.run(service.new_job(), events.append)
    assert job.state is JobState.SUCCEEDED
    assert events == [ProgressEvent(1, 10, "/a")]


def test_engine_error_is_recorded_not_raised():
    service = BackupService(FakeEngine(RepositoryLocked("locked")), REPO, ("/home",))
    job = service.run(service.new_job())
    assert (job.state, job.message) == (JobState.FAILED, "locked")


def test_backup_without_repository_fails_job():
    service = BackupService(FakeEngine(), None, ("/home",))
    assert service.run(service.new_job()).state is JobState.FAILED


def test_new_jobs_have_unique_ids():
    service = BackupService(FakeEngine(), REPO, ("/home",), ("*.tmp",))
    first, second = service.new_job(), service.new_job()
    assert first.id != second.id
    assert first.excludes[0] == "*.tmp"


def test_a_job_never_includes_the_repository_itself_so_a_destination_inside_the_sources_is_not_copied():
    service = BackupService(FakeEngine(), REPO, ("/home",), ("*.tmp",))

    assert service.new_job().excludes == ("*.tmp", "pp:/r")


def test_the_excluded_repository_path_is_normalized():
    service = BackupService(FakeEngine(), Repository("/home/u//backups/./repo/"), ("/home/u",))

    assert service.new_job().excludes == ("pp:/home/u/backups/repo",)


def test_a_job_without_a_repository_excludes_only_what_was_asked():
    service = BackupService(FakeEngine(), None, ("/home",), ("*.tmp",))

    assert service.new_job().excludes == ("*.tmp",)


def test_prune_applies_policy():
    engine = FakeEngine()
    assert PruneService(engine, REPO, RetentionPolicy()).run()
    assert engine.pruned == [RetentionPolicy()]


@pytest.mark.parametrize(("repo", "policy"), [(None, RetentionPolicy()), (REPO, RetentionPolicy(0, 0, 0, 0))])
def test_prune_noop_cases(repo, policy):
    engine = FakeEngine()
    assert not PruneService(engine, repo, policy).run()
    assert engine.pruned == []
