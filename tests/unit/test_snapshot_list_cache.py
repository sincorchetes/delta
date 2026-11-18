"""The list of snapshots is asked of borg once, then remembered until it can have changed."""

import json

import pytest

from delta.domain.backup_job import BackupJob
from delta.domain.errors import EngineError
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy
from delta.infrastructure.borg_runner import SNAPSHOTS_TTL, BorgRunner

A, B = Repository("/a"), Repository("/b")
JOB = BackupJob("j", ("/home/u",))


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class CountingRunner(BorgRunner):
    """Answers every `borg list` with one archive and counts how often it was asked."""

    def __init__(self, clock, fail=None):
        super().__init__(clock=clock)
        self.asked = 0
        self.fail = fail

    def _run(self, argv, repo, cwd=None, on_progress=None):
        if "list" in argv:
            self.asked += 1
            return json.dumps({"archives": [{"id": "i", "name": "n", "time": "2026-01-01T00:00:00.000000"}]})
        if self.fail:
            raise self.fail
        return ""


@pytest.fixture
def clock():
    return Clock()


def test_borg_is_asked_once_while_the_list_is_fresh(clock):
    runner = CountingRunner(clock)
    first = runner.list_snapshots(A)
    clock.now = SNAPSHOTS_TTL - 1
    assert runner.list_snapshots(A) == first
    assert runner.asked == 1


def test_it_is_asked_again_once_the_time_is_up(clock):
    runner = CountingRunner(clock)
    runner.list_snapshots(A)
    clock.now = SNAPSHOTS_TTL
    runner.list_snapshots(A)
    assert runner.asked == 2


def test_callers_cannot_spoil_what_is_remembered(clock):
    runner = CountingRunner(clock)
    runner.list_snapshots(A).clear()
    assert len(runner.list_snapshots(A)) == 1


def test_each_repository_has_its_own_list(clock):
    runner = CountingRunner(clock)
    runner.list_snapshots(A)
    runner.list_snapshots(B)
    assert runner.asked == 2


def test_a_new_backup_makes_it_forget(clock):
    runner = CountingRunner(clock)
    runner.list_snapshots(A)
    runner.create(A, JOB)
    runner.list_snapshots(A)
    assert runner.asked == 2


def test_a_failed_backup_makes_it_forget_too(clock):
    runner = CountingRunner(clock, fail=EngineError("boom"))
    runner.list_snapshots(A)
    with pytest.raises(EngineError):
        runner.create(A, JOB)
    runner.list_snapshots(A)
    assert runner.asked == 2


def test_pruning_makes_it_forget(clock):
    runner = CountingRunner(clock)
    runner.list_snapshots(A)
    runner.prune(A, RetentionPolicy())
    runner.list_snapshots(A)
    assert runner.asked == 2


def test_forgetting_one_repository_keeps_the_other(clock):
    runner = CountingRunner(clock)
    runner.list_snapshots(A)
    runner.list_snapshots(B)
    runner.prune(A, RetentionPolicy())
    runner.list_snapshots(B)
    assert runner.asked == 2
