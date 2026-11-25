"""A drive that is not connected is not a failed backup: it has an error, a state and messages of its own."""

import pytest

from delta.domain.backup_job import BackupJob, JobState
from delta.domain.errors import DeltaError, DestinationUnavailable, RepositoryNotFound
from delta.i18n import _ as translate
from destination_unavailable_support import EMPTY, MISSING


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
