import threading
import time

import gi
import pytest

gi.require_version("Gio", "2.0")
from gi.repository import GLib

from delta.daemon.job_runner import JobAlreadyRunning, JobRunner


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


def test_runs_immediately_when_idle(runner):
    called = []
    runner.when_idle(lambda: called.append(1))
    assert called == [1]


def test_waits_for_the_running_job_and_never_interrupts_it(runner):
    release, finished, called = threading.Event(), threading.Event(), []

    def task(on_progress):
        release.wait(5)
        finished.set()
        return True, ""

    runner.submit("job", task)
    runner.when_idle(lambda: called.append(finished.is_set()))

    assert called == []
    release.set()
    assert iterate_until(lambda: called)
    assert called == [True]


def test_repeated_registrations_coalesce(runner):
    release, count = threading.Event(), []
    runner.submit("job", lambda on_progress: (release.wait(5) or True, ""))

    def callback():
        count.append(1)

    for _ in range(3):
        runner.when_idle(callback)
    release.set()

    assert iterate_until(lambda: count)
    iterate_until(lambda: False, timeout=0.2)
    assert count == [1]


def test_callback_registered_during_job_survives_a_failing_job(runner):
    called = []

    def failing(on_progress):
        runner.when_idle(lambda: called.append(1))
        return False, "boom"

    runner.submit("job", failing)

    assert iterate_until(lambda: called)


def test_a_job_submitted_for_when_idle_starts_at_once_if_nothing_runs(runner):
    ran = []

    runner.submit_when_idle("job", lambda on_progress: (ran.append(1) or True, ""))

    assert iterate_until(lambda: ran)


def test_a_job_submitted_for_when_idle_waits_for_the_running_one_without_stopping_it(runner):
    release, order = threading.Event(), []

    def first(on_progress):
        release.wait(5)
        order.append("first")
        return True, ""

    runner.submit("one", first)
    runner.submit_when_idle("two", lambda on_progress: (order.append("second") or True, ""))

    assert order == []
    release.set()
    assert iterate_until(lambda: order == ["first", "second"])


def test_a_job_that_loses_the_race_to_another_waits_for_the_next_gap(runner):
    ran, refused = [], []
    submit = runner.submit

    def flaky(job_id, task, records_backup=False):
        if not refused:
            refused.append(1)
            raise JobAlreadyRunning()
        submit(job_id, task, records_backup)

    runner.submit = flaky
    runner.submit_when_idle("job", lambda on_progress: (ran.append(1) or True, ""))

    assert iterate_until(lambda: ran) and refused == [1]


def test_only_a_backup_counts_as_a_backup_running(runner):
    release, seen = threading.Event(), []

    def task(on_progress):
        seen.append(runner.backup_running)
        release.wait(5)
        return True, ""

    runner.submit("backup", task, records_backup=True)
    assert iterate_until(lambda: seen) and seen == [True]
    release.set()
    assert iterate_until(lambda: runner.status == "idle") and runner.backup_running is False

    release.clear()
    seen.clear()
    runner.submit("restore", task)
    assert iterate_until(lambda: seen) and seen == [False]
    release.set()


def test_a_backup_known_from_the_repository_seeds_the_last_backup(runner):
    runner.seed_last_backup(1_700_000_000)
    assert runner.last_backup == 1_700_000_000


def test_seeding_never_moves_the_last_backup_backwards(runner):
    runner.seed_last_backup(2_000)
    runner.seed_last_backup(1_000)
    assert runner.last_backup == 2_000


def test_clearing_the_error_forgets_the_last_failure(runner):
    runner.last_error = "locked"
    runner.clear_error()
    assert runner.last_error == ""


def test_a_check_is_the_status_while_it_runs_and_idle_after(runner):
    release = threading.Event()

    def task(on_progress):
        release.wait(5)
        return True, ""

    runner.submit("job", task, checking=True)
    assert runner.status == "checking"

    release.set()
    assert iterate_until(lambda: runner.status == "idle")


def test_a_backup_is_running_and_not_checking(runner):
    release = threading.Event()
    runner.submit("job", lambda on_progress: (release.wait(5), (True, ""))[1], records_backup=True)

    assert runner.status == "running"

    release.set()
    assert iterate_until(lambda: runner.status == "idle")
