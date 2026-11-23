"""A job that waits for its destination says why; one that does not has no reason to give."""

import pytest

from delta.domain.backup_job import BackupJob
from delta.domain.destination import DestinationState
from delta.domain.errors import DestinationUnavailable


def test_a_job_that_waits_gives_the_reason_it_was_given():
    job = BackupJob("j", ("/home",))
    error = DestinationUnavailable("/media/disk/delta", DestinationState.MISSING)
    job.wait_for_destination(error)

    assert job.why_unavailable() is error


def test_a_job_that_is_not_waiting_has_no_reason_and_asking_for_it_is_a_mistake():
    with pytest.raises(ValueError, match="not waiting for a destination"):
        BackupJob("j", ("/home",)).why_unavailable()
