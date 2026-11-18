"""The error answers of the daemon's job and query calls, without a bus: a stand-in invocation."""

import pytest

from delta.daemon import job_calls, query_calls
from delta.daemon.job_runner import JobAlreadyRunning
from delta.domain.errors import InvalidPath


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
    def __init__(self, busy=False):
        self.busy = busy
        self.submitted = []

    def submit(self, job_id, task, records_backup=False):
        if self.busy:
            raise JobAlreadyRunning()
        self.submitted.append((job_id, task, records_backup))


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
