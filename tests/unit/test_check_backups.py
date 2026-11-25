"""Checking that the backups can be read: what is asked of the engine, and what the findings come to."""

import pytest

from delta.application.check_service import CheckService
from delta.domain.destination import DestinationState
from delta.domain.errors import DestinationUnavailable, EngineError, RepositoryDamaged, RepositoryLocked
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

REPO = Repository("/media/disk/delta")


class Engine:
    def __init__(self):
        self.checked = []

    def check(self, repo):
        self.checked.append(repo)


class Probe:
    def __init__(self, state=DestinationState.AVAILABLE):
        self.answer, self.asked = state, []

    def state(self, repo, out_of_space=False):
        self.asked.append(repo)
        return self.answer


def test_a_repository_that_can_be_used_is_checked():
    engine, probe = Engine(), Probe()

    assert CheckService(engine, REPO, probe).run() is True
    assert engine.checked == [REPO] and probe.asked == [REPO]


def test_without_a_repository_nothing_is_touched():
    engine, probe = Engine(), Probe()

    assert CheckService(engine, None, probe).run() is False
    assert engine.checked == [] and probe.asked == []


@pytest.mark.parametrize("state", [s for s in DestinationState if s is not DestinationState.AVAILABLE])
def test_a_place_that_cannot_be_used_is_said_and_the_engine_is_not_asked(state):
    engine = Engine()

    with pytest.raises(DestinationUnavailable) as raised:
        CheckService(engine, REPO, Probe(state)).run()

    assert raised.value.state is state and raised.value.location == REPO.location and engine.checked == []


class Runner(BorgRunner):
    def __init__(self, error=None):
        super().__init__()
        self.error, self.argv = error, None

    def _run(self, argv, repo, cwd=None, on_progress=None):
        self.argv = argv
        if self.error:
            raise self.error
        return ""


def test_the_engine_checks_the_repository_only():
    runner = Runner()
    runner.check(REPO)

    assert runner.argv == ["borg", "check", "--repository-only", REPO.location]


def test_what_the_check_finds_is_a_damaged_repository_with_what_borg_said():
    with pytest.raises(RepositoryDamaged) as raised:
        Runner(EngineError("Finished full repository check, errors found.", 1)).check(REPO)

    assert "Finished full repository check, errors found." in str(raised.value)
    assert str(raised.value).startswith("The check found problems in your backups.")


def test_a_failure_that_is_not_a_finding_is_not_made_one():
    with pytest.raises(RepositoryLocked):
        Runner(RepositoryLocked("locked")).check(REPO)


def test_what_borg_said_is_shortened():
    assert str(RepositoryDamaged("x" * 1000)).endswith("x" * 300) and "x" * 301 not in str(RepositoryDamaged("x" * 1000))
