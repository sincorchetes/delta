import pytest

from delta.application.unlock_service import UnlockService
from delta.domain.destination import DestinationState
from delta.domain.errors import DestinationUnavailable, RepositoryLocked, is_lock_message
from delta.domain.repository import Repository
from delta.infrastructure import borg_commands as commands
from delta.infrastructure.borg_parsing import error_for

REPO = Repository("/home/me/repo")


@pytest.mark.parametrize(
    "text",
    [
        "Failed to create/acquire the lock /repo/lock.exclusive (timeout).",
        "Cannot lock: failed",
        "lock timeout",
    ],
)
def test_borgs_lock_failures_are_recognised(text):
    assert is_lock_message(text)


@pytest.mark.parametrize(
    "text",
    ["", "repository locked", "The passphrase is incorrect."],
)
def test_other_messages_are_not_lock_failures(text):
    assert not is_lock_message(text)


def test_the_engine_maps_a_lock_failure_to_repository_locked():
    assert isinstance(error_for(2, "Failed to create/acquire the lock /r/lock.exclusive"), RepositoryLocked)


def test_break_lock_is_a_plain_argv_for_the_repository_only():
    assert commands.break_lock(REPO) == ["borg", "break-lock", REPO.location]


class Engine:
    def __init__(self):
        self.broken = []

    def break_lock(self, repo):
        self.broken.append(repo)


class Probe:
    def __init__(self, state=DestinationState.AVAILABLE):
        self.answer, self.asked = state, []

    def state(self, repo, out_of_space=False):
        self.asked.append(repo)
        return self.answer


def test_unlocking_breaks_the_lock_of_the_configured_repository():
    engine = Engine()
    assert UnlockService(engine, REPO, Probe()).run() is True
    assert engine.broken == [REPO]


def test_without_a_repository_nothing_is_touched():
    engine, probe = Engine(), Probe()
    assert UnlockService(engine, None, probe).run() is False
    assert engine.broken == [] and probe.asked == []


@pytest.mark.parametrize("state", [s for s in DestinationState if s is not DestinationState.AVAILABLE])
def test_a_place_that_cannot_be_used_is_said_and_nothing_is_touched(state):
    engine, probe = Engine(), Probe(state)

    with pytest.raises(DestinationUnavailable) as raised:
        UnlockService(engine, REPO, probe).run()

    assert raised.value.state is state and raised.value.location == REPO.location
    assert engine.broken == [] and probe.asked == [REPO]
