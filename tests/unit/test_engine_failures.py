"""A failure of the engine is told by what it says: the number of the system's error, and not by which words it happens to contain."""

import logging

import pytest

from delta.application.backup_service import BackupService
from delta.domain.backup_job import JobState
from delta.domain.destination import DestinationState
from delta.domain.errors import EngineError, RepositoryLocked, engine_errno, is_lock_message, state_from_error
from delta.domain.repository import Repository
from delta.infrastructure.borg_parsing import crash_reason, error_for

LOCATION = "/media/disk/delta"
READ_ONLY = f"Failed to create/acquire the lock {LOCATION}/lock.exclusive ([Errno 30] Read-only file system: '{LOCATION}/lock.exclusive.m_x.tmp')."
DENIED = f"[Errno 13] Permission denied: '{LOCATION}/data/0/1'"
CRASH = """Local Exception
Traceback (most recent call last):
  File "/nix/store/x/borg/archiver.py", line 5759, in main
    exit_code = archiver.run(args)
  File "/nix/store/x/borg/archiver.py", line 5655, in run
    return set_ec(func(args))
OSError: [Errno 5] Input/output error
Platform: Linux tank0 6.18.63 #1 SMP x86_64
Linux: Unknown Linux
Borg: Borg 1.4.4  Python: CPython 3.13.18
"""


@pytest.mark.parametrize(
    "text, number",
    [
        ("[Errno 30] Read-only file system", 30),
        ("x ([Errno 5] Input/output error) y", 5),
        ("[Errno 13] Permission denied, then [Errno 5] Input/output error", 13),
        ("no number here", None),
        ("Errno 5 without brackets", None),
        ("", None),
    ],
)
def test_the_number_of_the_systems_error_is_read_from_what_the_engine_said(text, number):
    assert engine_errno(text) == number


@pytest.mark.parametrize(
    "text, is_lock",
    [
        ("Failed to create/acquire the lock /repo/lock.exclusive (timeout).", True),
        ("Cannot lock: failed", True),
        (READ_ONLY, False),  # the same words, but the place is read-only: not a lock held by anybody
        ("Failed to create/acquire the lock /r/lock.exclusive ([Errno 13] Permission denied)", False),
        ("", False),
    ],
)
def test_a_lock_is_one_that_is_held_and_not_one_that_could_not_be_made_for_an_error_of_the_system(text, is_lock):
    assert is_lock_message(text) is is_lock


def test_a_lock_that_could_not_be_made_because_the_place_is_read_only_is_not_a_locked_repository():
    assert not isinstance(error_for(2, READ_ONLY), RepositoryLocked)


@pytest.mark.parametrize(
    "text, location, state",
    [
        ("Insufficient free space to complete transaction (required: 545.43 MB, available: 263.97 MB).", LOCATION, DestinationState.FULL),
        ("OSError: [Errno 5] Input/output error", LOCATION, DestinationState.IO_ERROR),
        ("OSError: [Errno 6] No such device or address", "/anywhere", DestinationState.IO_ERROR),
        ("OSError: [Errno 19] No such device", LOCATION, DestinationState.IO_ERROR),
        ("OSError: [Errno 116] Stale file handle", LOCATION, DestinationState.IO_ERROR),
        (READ_ONLY, LOCATION, DestinationState.READ_ONLY),
        (READ_ONLY, "/another/place", None),  # a read-only file system that is not the repository's
        (DENIED, LOCATION, DestinationState.DENIED),
        (DENIED.replace("[Errno 13]", "[Errno 1]"), LOCATION, DestinationState.DENIED),
        (DENIED, "/another/place", None),
        ("[Errno 28] No space left on device", LOCATION, None),  # it can be the home folder: left to the probe
        ("Input/output error", LOCATION, None),  # no number: nothing to go by
        ("", LOCATION, None),
    ],
)
def test_what_a_failure_says_about_the_place_of_the_repository(text, location, state):
    assert state_from_error(text, location) is state


class Probe:
    def state(self, repo, out_of_space=False):
        return DestinationState.AVAILABLE


class Engine:
    def __init__(self, error):
        self.error = error

    def create(self, repo, job, name=None, on_progress=None):
        raise self.error


def failed_with(text):
    backup = BackupService(Engine(EngineError(text)), Repository(LOCATION), ("/home",), destination=Probe())
    job = backup.new_job()
    backup.run(job)
    return job


@pytest.mark.parametrize(
    "text, state",
    [
        (READ_ONLY, DestinationState.READ_ONLY),
        ("OSError: [Errno 5] Input/output error", DestinationState.IO_ERROR),
        (DENIED, DestinationState.DENIED),
    ],
)
def test_a_failure_that_names_the_place_makes_the_backup_wait_with_that_cause_when_the_probe_sees_nothing_wrong(text, state):
    job = failed_with(text)

    assert job.state is JobState.UNAVAILABLE and job.unavailable.state is state


def test_a_failure_about_somewhere_else_is_still_a_failure_of_the_backup():
    job = failed_with("OSError: [Errno 13] Permission denied: '/home/u/.cache/borg/x'")

    assert job.state is JobState.FAILED


# --- the report of an internal error of Borg ---------------------------------------------------------


def test_the_line_that_names_the_exception_is_the_reason():
    assert crash_reason(CRASH) == "OSError: [Errno 5] Input/output error"


def test_of_chained_exceptions_the_last_one_is_the_reason():
    chained = (
        "Traceback (most recent call last):\n  File \"a.py\", line 1\nOSError: [Errno 5] first\n\n"
        "During handling of the above exception, another exception occurred:\n\n"
        "Traceback (most recent call last):\n  File \"b.py\", line 2\nValueError: the second\nPlatform: Linux"
    )

    assert crash_reason(chained) == "ValueError: the second"


def test_the_reason_is_found_even_when_the_report_has_no_platform_lines():
    assert crash_reason("Traceback (most recent call last):\n  File \"a.py\", line 1\nOSError: [Errno 5] gone") == "OSError: [Errno 5] gone"


def test_lines_with_a_single_space_or_tab_of_indentation_and_one_character_lines_are_not_the_reason():
    report = "Traceback (most recent call last):\nOSError: the reason\n detail\n\tmore\nx\nPlatform: Linux"

    assert crash_reason(report) == "x"


def test_text_that_is_not_a_report_of_a_crash_has_no_reason():
    assert crash_reason("Repository /x does not exist.") is None
    assert crash_reason("Traceback (most recent call last):\n  File \"a.py\", line 1") is None


def test_a_crash_of_borg_is_told_in_one_line_and_its_report_is_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="delta.infrastructure.borg_parsing"):
        error = error_for(2, CRASH)

    assert isinstance(error, EngineError) and error.returncode == 2
    assert str(error) == "Borg stopped unexpectedly: OSError: [Errno 5] Input/output error"
    assert [record.getMessage() for record in caplog.records] == ["borg stopped with an internal error:\n" + CRASH.strip()]
