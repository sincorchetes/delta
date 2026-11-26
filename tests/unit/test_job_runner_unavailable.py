"""A destination that cannot be reached is a state of the daemon, not the last error: it ends by itself when it is back."""

import time

import gi
import pytest

gi.require_version("Gio", "2.0")
from gi.repository import GLib

from delta.daemon.job_runner import JobRunner
from delta.domain.destination import DestinationState
from delta.domain.errors import DestinationUnavailable, EngineError


class FakeConnection:
    def emit_signal(self, *args):
        return True


def iterate_until(predicate, timeout=5.0):
    context, deadline = GLib.MainContext.default(), time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)
    return predicate()


@pytest.fixture
def runner():
    return JobRunner(FakeConnection())


def finish(runner, task, records_backup=True):
    runner.submit("job", task, records_backup=records_backup)
    assert iterate_until(lambda: runner.status != "running")


def away(on_progress):
    raise DestinationUnavailable("/media/disk/delta", DestinationState.MISSING)


def done(on_progress):
    return True, ""


def broken(on_progress):
    raise EngineError("it broke")


def test_a_runner_starts_with_nothing_unavailable(runner):
    assert (runner.status, runner.unavailable, runner.last_error) == ("idle", "", "")


def test_a_destination_that_cannot_be_reached_is_the_status_and_not_an_error(runner):
    finish(runner, away)

    assert runner.status == "unavailable"
    assert runner.unavailable == "/media/disk/delta"
    assert runner.last_error == "" and runner.last_backup == 0


def test_while_a_job_runs_it_is_running_even_if_the_last_one_found_the_drive_away(runner):
    finish(runner, away)
    release = []

    def slow(on_progress):
        while not release:
            time.sleep(0.005)
        return True, ""

    runner.submit("again", slow, records_backup=True)

    assert runner.status == "running"
    release.append(1)
    assert iterate_until(lambda: runner.status != "running")


def test_a_good_backup_ends_it(runner):
    finish(runner, away)

    finish(runner, done)

    assert (runner.status, runner.unavailable, runner.last_error) == ("idle", "", "")
    assert runner.last_backup > 0


def test_a_failure_ends_it_and_is_the_last_error(runner):
    finish(runner, away)

    finish(runner, broken)

    assert (runner.status, runner.unavailable, runner.last_error) == ("idle", "", "it broke")


def test_it_replaces_the_last_error_of_a_failure_that_came_before(runner):
    finish(runner, broken)

    finish(runner, away)

    assert (runner.status, runner.last_error) == ("unavailable", "")


def test_a_backup_done_with_something_to_say_leaves_all_of_it_in_the_log(runner, caplog):
    said = "/home/user/.local/share/Telegram/tdata/socket: file changed while we backed it up\n" + "x" * 400

    with caplog.at_level("WARNING", logger="delta.daemon.job_runner"):
        finish(runner, lambda on_progress: (True, said))

    assert said in caplog.text and runner.last_error == "" and runner.last_backup > 0


def test_a_clean_backup_logs_no_warning(runner, caplog):
    with caplog.at_level("WARNING", logger="delta.daemon.job_runner"):
        finish(runner, done)

    assert caplog.text == ""


def test_a_job_that_is_not_a_backup_leaves_the_state_alone(runner):
    finish(runner, away)

    finish(runner, away, records_backup=False)  # for example the creation of a repository, which a drive does not decide on
    finish(runner, done, records_backup=False)

    assert runner.status == "unavailable"


@pytest.mark.parametrize("state", list(DestinationState)[1:])
def test_the_reason_is_kept_for_the_window_to_say_it(runner, state):
    def blocked(on_progress):
        raise DestinationUnavailable("/media/disk/delta", state)

    finish(runner, blocked)

    assert (runner.status, runner.unavailable_reason) == ("unavailable", state.value)


def test_the_reason_goes_with_the_state(runner):
    finish(runner, away)
    assert runner.unavailable_reason == "missing"

    finish(runner, done)

    assert runner.unavailable_reason == ""


def test_a_place_that_is_known_to_be_unusable_is_the_status_before_any_backup_tried_it():
    state = [DestinationState.EMPTY]
    runner = JobRunner(FakeConnection(), lambda: state[0])

    assert (runner.status, runner.reason, runner.unavailable) == ("unavailable", "empty", "")

    state[0] = DestinationState.AVAILABLE

    assert (runner.status, runner.reason) == ("idle", "")


def test_what_a_backup_found_is_the_reason_even_if_the_place_looks_fine_now():
    runner = JobRunner(FakeConnection(), lambda: DestinationState.AVAILABLE)
    runner.unavailable, runner.unavailable_reason = "/media/disk/delta", "full"

    assert (runner.status, runner.reason) == ("unavailable", "full")


def test_a_running_job_is_running_whatever_the_place_looks_like():
    runner = JobRunner(FakeConnection(), lambda: DestinationState.MISSING)
    runner._running = True

    assert runner.status == "running"
