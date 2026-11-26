"""The error answers of the daemon's job and query calls, without a bus: a stand-in invocation."""

import logging
from types import SimpleNamespace

import pytest

from delta.daemon import job_calls, query_calls
from delta.daemon.job_runner import JobAlreadyRunning
from delta.domain.errors import BackupInterrupted, EngineError, InvalidPath


class Invocation:
    def __init__(self):
        self.errors = []
        self.values = []

    def return_dbus_error(self, name, message):
        self.errors.append((name, message))

    def return_value(self, value):
        self.values.append(value)


class Parameters:
    def __init__(self, *values):
        self.values = values

    def unpack(self):
        return self.values


class Jobs:
    def __init__(self, busy=False, checking=False):
        self.busy, self.checking_now = busy, checking
        self.submitted, self.kinds, self.cleared = [], [], 0

    def submit(self, job_id, task, records_backup=False, checking=False):
        if self.busy:
            raise JobAlreadyRunning()
        self.submitted.append((job_id, task, records_backup))
        self.kinds.append(checking)

    @property
    def checking(self):
        return self.checking_now

    def clear_error(self):
        self.cleared += 1


class PathService:
    """Stands in for any service whose `prepare` refuses a path."""

    def prepare(self, *_args):
        raise InvalidPath("outside the home folder")

    prepare_in_place = prepare

    @staticmethod
    def new_job_id():
        return "job"


def answered(invocation):
    assert len(invocation.errors) == 1 and not invocation.values
    return invocation.errors[0][0]


# --- jobs ----------------------------------------------------------------------------------------


def test_a_second_job_is_told_the_daemon_is_busy():
    invocation = Invocation()

    job_calls.submit_job(Jobs(busy=True), invocation, "id", lambda progress: (True, ""))

    assert answered(invocation) == job_calls.ERROR_BUSY


@pytest.mark.parametrize(
    ("call", "parameters"),
    [
        (job_calls.start_restore, Parameters("first", "/home/u/a", "/home/u/t")),
        (lambda *a: job_calls.start_restore_beside(*a, replace=False), Parameters("first", "/home/u/a")),
        (job_calls.start_restore_deleted, Parameters("first", "/home/u/folder")),
        (job_calls.start_preview, Parameters("first", "/home/u/a")),
    ],
)
def test_a_job_without_its_service_is_unavailable(call, parameters):
    invocation = Invocation()

    call(None, None, parameters, invocation)

    assert answered(invocation) == job_calls.ERROR_UNAVAILABLE


@pytest.mark.parametrize(
    ("call", "parameters"),
    [
        (job_calls.start_restore, Parameters("first", "/etc/passwd", "/etc")),
        (lambda *a: job_calls.start_restore_beside(*a, replace=True), Parameters("first", "/etc/passwd")),
        (job_calls.start_restore_deleted, Parameters("first", "/etc")),
        (job_calls.start_preview, Parameters("first", "/etc/passwd")),
    ],
)
def test_a_path_the_service_refuses_is_an_invalid_path_and_starts_no_job(call, parameters):
    jobs, invocation = Jobs(), Invocation()

    call(jobs, PathService(), parameters, invocation)

    assert answered(invocation) == job_calls.ERROR_INVALID_PATH
    assert jobs.submitted == []


# --- queries -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("call", "parameters"),
    [
        (query_calls.list_versions, Parameters("/home/u/a")),
        (query_calls.list_folder, Parameters("first", "/home/u")),
        (query_calls.list_deleted, Parameters("first", "/home/u")),
        (query_calls.list_changed, Parameters("first", "/home/u")),
        (query_calls.search_folder, Parameters("first", "/home/u", "needle")),
    ],
)
def test_a_query_without_its_service_is_unavailable(call, parameters):
    invocation = Invocation()

    call(None, parameters, invocation)

    assert answered(invocation) == query_calls.ERROR_UNAVAILABLE


# --- unlocking and checking ----------------------------------------------------------------------


class Service:
    """Stands in for the unlock and the check services: `run` says whether there was a repository, or raises."""

    def __init__(self, found=True, error=None):
        self.found, self.error = found, error

    def run(self):
        if self.error:
            raise self.error
        return self.found


def finished(jobs):
    return jobs.submitted[0][1](lambda event: None)


@pytest.mark.parametrize("call", [job_calls.start_unlock, job_calls.start_check])
def test_unlocking_or_checking_without_the_service_is_unavailable(call):
    invocation = Invocation()

    call(Jobs(), None, invocation)
    call(None, Service(), invocation)

    assert [name for name, _message in invocation.errors] == [job_calls.ERROR_UNAVAILABLE] * 2 and not invocation.values


def test_unlocking_forgets_the_old_failure_and_says_nothing_else():
    jobs, invocation = Jobs(), Invocation()

    job_calls.start_unlock(jobs, Service(), invocation)

    assert finished(jobs) == (True, "") and jobs.cleared == 1 and jobs.kinds == [False] and len(invocation.values) == 1


def test_unlocking_with_no_repository_says_so_and_keeps_the_failure():
    jobs = Jobs()
    job_calls.start_unlock(jobs, Service(found=False), Invocation())

    assert finished(jobs) == (False, "No backup repository is set up.") and jobs.cleared == 0


def test_a_check_is_a_job_of_its_own_kind_that_says_how_it_went():
    jobs, invocation = Jobs(), Invocation()

    job_calls.start_check(jobs, Service(), invocation)

    assert finished(jobs) == (True, "Your backups were checked and no problems were found.")
    assert jobs.kinds == [True] and len(invocation.values) == 1


def test_a_check_says_in_the_log_when_it_starts_and_how_it_ended(caplog):
    with caplog.at_level(logging.INFO, logger="delta.daemon.job_calls"):
        for service in (Service(), Service(error=BackupInterrupted("stopped"))):
            jobs = Jobs()
            job_calls.start_check(jobs, service, Invocation())
            finished(jobs)

    assert [record.getMessage() for record in caplog.records] == [
        "checking that the backups can be read",
        "the check of the backups found no problems",
        "checking that the backups can be read",
        "the check of the backups was cancelled",
    ]


def test_a_check_with_no_repository_says_so():
    jobs = Jobs()
    job_calls.start_check(jobs, Service(found=False), Invocation())

    assert finished(jobs) == (False, "No backup repository is set up.")


def test_a_check_that_is_stopped_on_request_says_it_was_cancelled():
    jobs = Jobs()
    job_calls.start_check(jobs, Service(error=BackupInterrupted("stopped")), Invocation())

    assert finished(jobs) == (True, "The check was cancelled.")


def test_a_check_while_another_job_runs_is_told_the_daemon_is_busy():
    invocation = Invocation()

    job_calls.start_check(Jobs(busy=True), Service(), invocation)

    assert answered(invocation) == job_calls.ERROR_BUSY


def test_cancelling_stops_a_check_that_is_running():
    stopped, invocation = [], Invocation()

    job_calls.cancel_check(Jobs(checking=True), lambda: stopped.append(1), invocation)

    assert stopped == [1] and len(invocation.values) == 1


def test_cancelling_never_stops_anything_else():
    stopped, invocation = [], Invocation()

    job_calls.cancel_check(Jobs(checking=False), lambda: stopped.append(1), invocation)

    assert stopped == [] and len(invocation.values) == 1


def test_cancelling_without_the_job_runner_does_nothing():
    stopped, invocation = [], Invocation()

    job_calls.cancel_check(None, lambda: stopped.append(1), invocation)

    assert stopped == [] and len(invocation.values) == 1


@pytest.fixture
def at_once(monkeypatch):
    """A query that runs where it is called and answers at once, instead of on a thread and the main loop."""
    monkeypatch.setattr(query_calls, "threading", SimpleNamespace(Thread=lambda target, daemon: SimpleNamespace(start=target)))
    monkeypatch.setattr(query_calls, "GLib", SimpleNamespace(idle_add=lambda call, *args: call(*args)))


def failing(error):
    def produce():
        raise error

    return produce


def test_a_query_that_fails_is_answered_and_logged_with_what_it_said(at_once, caplog):
    invocation = Invocation()

    with caplog.at_level(logging.WARNING, logger="delta.daemon.query_calls"):
        query_calls.run_query(invocation, failing(EngineError("repository is locked")))

    assert invocation.errors == [(query_calls.ERROR_FAILED, "repository is locked")]
    assert [(r.levelname, r.getMessage()) for r in caplog.records] == [("WARNING", "a query failed: repository is locked")]


def test_a_query_that_crashes_is_still_answered_and_the_traceback_is_logged(at_once, caplog):
    invocation = Invocation()

    with caplog.at_level(logging.WARNING, logger="delta.daemon.query_calls"):
        query_calls.run_query(invocation, failing(KeyError("snapshot")))

    assert invocation.errors == [(query_calls.ERROR_FAILED, "unexpected error")]
    record = caplog.records[0]
    assert (record.levelname, record.getMessage()) == ("ERROR", "a query crashed")
    assert record.exc_info is not None and record.exc_info[0] is KeyError


def test_a_path_that_is_refused_is_not_a_failure_to_log(at_once, caplog):
    invocation = Invocation()

    with caplog.at_level(logging.INFO, logger="delta.daemon.query_calls"):
        query_calls.run_query(invocation, failing(InvalidPath("outside the home folder")))

    assert invocation.errors == [(query_calls.ERROR_INVALID_PATH, "outside the home folder")]
    assert caplog.records == []
