"""A drive that is not connected is not a failed backup: it has an error, a state and messages of its own."""

import pytest

from delta.application.backup_service import BackupService
from delta.domain.backup_job import BackupJob, JobState
from delta.domain.destination import DestinationState
from delta.domain.errors import (
    BackupWarning,
    DeltaError,
    DestinationUnavailable,
    EngineError,
    RepositoryNotFound,
    is_full_message,
)
from delta.domain.repository import Repository
from delta.i18n import _ as translate

REPO = Repository("/media/disk/delta")
MISSING, EMPTY, AVAILABLE = DestinationState.MISSING, DestinationState.EMPTY, DestinationState.AVAILABLE


class Probe:
    """Answers with each state in turn, and with the last one from then on."""

    def __init__(self, *states):
        self.states, self.asked, self.out_of_space = list(states), [], []

    def state(self, repo, out_of_space=False):
        self.asked.append(repo)
        self.out_of_space.append(out_of_space)
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]


class Engine:
    def __init__(self, error=None):
        self.error, self.calls = error, 0

    def create(self, repo, job, name=None, on_progress=None):
        self.calls += 1
        if self.error:
            raise self.error
        return "archive"


def service(engine, *states, repo=REPO):
    return BackupService(engine, repo, ("/home",), destination=Probe(*states) if states else None)


# --- the error ------------------------------------------------------------------------------------


def test_it_is_an_error_of_its_own_and_not_a_repository_that_was_not_found():
    assert issubclass(DestinationUnavailable, DeltaError)
    assert not issubclass(DestinationUnavailable, RepositoryNotFound)
    assert not issubclass(RepositoryNotFound, DestinationUnavailable)


def test_it_says_where_and_why():
    error = DestinationUnavailable("/media/disk/delta", MISSING)

    assert (error.location, error.state) == ("/media/disk/delta", MISSING)
    assert str(error) == translate("The place where your backups are kept is not available: {location}").format(
        location="/media/disk/delta"
    )


def test_it_tells_what_to_do_according_to_why():
    assert DestinationUnavailable("/x", MISSING).hint == translate(
        "The folder is not there. Connect the drive that holds your backups."
    )
    assert DestinationUnavailable("/x", EMPTY).hint == translate("The folder is empty. Connect the drive that was there.")


# --- the state of a job ---------------------------------------------------------------------------


def job():
    return BackupJob("j", ("/home",))


def test_a_job_that_has_not_started_can_wait_for_the_destination():
    waiting, error = job(), DestinationUnavailable("/media/d", EMPTY)

    waiting.wait_for_destination(error)

    assert waiting.state is JobState.UNAVAILABLE and waiting.unavailable is error and waiting.message == str(error)


def test_a_job_that_is_running_can_wait_for_the_destination_when_the_drive_goes():
    running = job()
    running.start()

    running.wait_for_destination(DestinationUnavailable("/media/d", MISSING))

    assert running.state is JobState.UNAVAILABLE


@pytest.mark.parametrize("then", ["start", "succeed", "interrupt"])
def test_a_job_that_waited_does_not_go_on(then):
    waiting = job()
    waiting.wait_for_destination(DestinationUnavailable("/media/d", MISSING))

    with pytest.raises(ValueError):
        getattr(waiting, then)()


def test_a_job_that_waited_does_not_fail_or_warn_either():
    waiting = job()
    waiting.wait_for_destination(DestinationUnavailable("/media/d", MISSING))

    with pytest.raises(ValueError):
        waiting.fail("no")
    with pytest.raises(ValueError):
        waiting.warn("no")


# --- the backup service ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", [MISSING, EMPTY])
def test_a_destination_that_cannot_be_reached_is_not_asked_to_the_engine_and_is_not_a_failure(state):
    engine = Engine()
    backup = service(engine, state)
    waiting = backup.new_job()

    backup.run(waiting)

    assert waiting.state is JobState.UNAVAILABLE and engine.calls == 0
    assert (waiting.unavailable.location, waiting.unavailable.state) == (REPO.location, state)


def test_a_destination_that_can_be_reached_is_backed_up_as_usual():
    engine = Engine()
    backup = service(engine, AVAILABLE)
    ready = backup.new_job()

    backup.run(ready)

    assert ready.state is JobState.SUCCEEDED and engine.calls == 1


def test_without_a_probe_there_is_nothing_to_ask_and_a_failure_stays_a_failure():
    backup = service(Engine(RepositoryNotFound("Repository /x does not exist.")))
    failing = backup.new_job()

    backup.run(failing)

    assert failing.state is JobState.FAILED and failing.message == "Repository /x does not exist."
    assert backup.unreachable() is None


def test_when_the_drive_goes_while_the_engine_works_the_failure_is_the_drive_not_the_engine():
    engine, probe = Engine(EngineError("Input/output error")), Probe(AVAILABLE, MISSING)
    backup = BackupService(engine, REPO, ("/home",), destination=probe)
    working = backup.new_job()

    backup.run(working)

    assert working.state is JobState.UNAVAILABLE and engine.calls == 1 and len(probe.asked) == 2
    assert working.unavailable.state is MISSING


def test_an_engine_failure_with_the_drive_still_there_is_a_failure():
    backup = service(Engine(EngineError("it broke")), AVAILABLE)
    failing = backup.new_job()

    backup.run(failing)

    assert failing.state is JobState.FAILED and failing.message == "it broke"


def test_a_warning_is_a_warning_and_the_drive_is_not_asked_again():
    probe = Probe(AVAILABLE, MISSING)
    backup = BackupService(Engine(BackupWarning("1 file unreadable")), REPO, ("/home",), destination=probe)
    warned = backup.new_job()

    backup.run(warned)

    assert warned.state is JobState.WARNINGS and len(probe.asked) == 1


def test_with_no_repository_that_is_what_is_said_and_the_destination_is_not_asked():
    probe = Probe(MISSING)
    backup = BackupService(Engine(), None, ("/home",), destination=probe)
    unset = backup.new_job()

    backup.run(unset)

    assert unset.state is JobState.FAILED and unset.message == translate("no repository configured")
    assert probe.asked == [] and backup.unreachable() is None


# --- the other causes: full, read-only, no permission ---------------------------------------------------

FULL, READ_ONLY, DENIED = DestinationState.FULL, DestinationState.READ_ONLY, DestinationState.DENIED
OTHER_DRIVE = DestinationState.OTHER_DRIVE
NO_ROOM = "/h/test.flac: read: [Errno 28] No space left on device"


@pytest.mark.parametrize(
    "state, message",
    [
        (OTHER_DRIVE, "A drive is connected where your backups were kept, but they are not on it: /media/disk/delta"),
        (FULL, "The place where your backups are kept is full: /media/disk/delta"),
        (READ_ONLY, "The place where your backups are kept is read-only: /media/disk/delta"),
        (DENIED, "You cannot write in the place where your backups are kept: /media/disk/delta"),
        (MISSING, "The place where your backups are kept is not available: /media/disk/delta"),
        (EMPTY, "The place where your backups are kept is not available: /media/disk/delta"),
    ],
)
def test_each_cause_says_what_is_wrong_with_the_place(state, message):
    assert str(DestinationUnavailable("/media/disk/delta", state)) == message


@pytest.mark.parametrize(
    "state, hint",
    [
        (
            OTHER_DRIVE,
            "This is not the drive that holds your backups. Connect that one, or choose another place in the preferences.",
        ),
        (FULL, "There is no room left there. Free some space, or choose another place in the preferences."),
        (
            READ_ONLY,
            "It is mounted so that nothing can be written to it. Mount it again for writing, or choose another place in the preferences.",
        ),
        (
            DENIED,
            "You do not have permission to write there. Change its permissions, or choose another place in the preferences.",
        ),
        (EMPTY, "The folder is empty. Connect the drive that was there."),
        (MISSING, "The folder is not there. Connect the drive that holds your backups."),
    ],
)
def test_each_cause_has_a_hint_of_its_own(state, hint):
    assert DestinationUnavailable("/x", state).hint == hint


@pytest.mark.parametrize(
    "text, is_full",
    [
        (NO_ROOM, True),
        ("No space left on device", True),  # each of the four ways of saying it, alone
        ("[Errno 28] something", True),
        ("Disk quota exceeded", True),
        ("[Errno 122] something", True),
        ("NO SPACE LEFT", True),
        ("Input/output error", False),
        ("Repository /x does not exist.", False),
        ("", False),
    ],
)
def test_the_engine_saying_that_a_disk_has_no_room_is_recognised(text, is_full):
    assert is_full_message(text) is is_full


def test_a_failure_that_says_no_room_asks_the_probe_whether_it_was_the_destination_that_ran_out():
    probe = Probe(AVAILABLE, FULL)
    backup = BackupService(Engine(EngineError(NO_ROOM)), REPO, ("/home",), destination=probe)
    working = backup.new_job()

    backup.run(working)

    assert probe.out_of_space == [False, True]
    assert working.state is JobState.UNAVAILABLE and working.unavailable.state is FULL


def test_a_failure_that_does_not_say_so_asks_the_ordinary_question():
    probe = Probe(AVAILABLE)
    backup = BackupService(Engine(EngineError("Input/output error")), REPO, ("/home",), destination=probe)
    working = backup.new_job()

    backup.run(working)

    assert probe.out_of_space == [False, False] and working.state is JobState.FAILED


def test_no_room_somewhere_else_is_still_a_failure_of_the_backup():
    # the home folder, where the engine keeps its cache, ran out: the destination has room
    probe = Probe(AVAILABLE)
    backup = BackupService(Engine(EngineError(NO_ROOM)), REPO, ("/home",), destination=probe)
    working = backup.new_job()

    backup.run(working)

    assert working.state is JobState.FAILED and working.message == NO_ROOM


@pytest.mark.parametrize("state", [FULL, READ_ONLY, DENIED])
def test_a_place_that_cannot_be_written_to_at_the_start_waits_and_asks_the_engine_nothing(state):
    engine = Engine()
    backup = BackupService(engine, REPO, ("/home",), destination=Probe(state))
    waiting = backup.new_job()

    backup.run(waiting)

    assert waiting.state is JobState.UNAVAILABLE and waiting.unavailable.state is state and engine.calls == 0
