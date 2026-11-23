"""What the runner says on the bus, which is the contract of the D-Bus API: names, formats and exactly once."""

import logging
import threading
import time
from types import SimpleNamespace

import gi
import pytest

gi.require_version("Gio", "2.0")
from gi.repository import GLib

from delta.daemon import job_runner
from delta.daemon.job_runner import JobRunner
from delta.domain.destination import DestinationState
from delta.domain.errors import DestinationUnavailable

PATH, INTERFACE = "/io/github/sincorchetes/Delta/Service1", "io.github.sincorchetes.Delta.Service1"


class Wire:
    def __init__(self):
        self.sent = []

    def emit_signal(self, destination, path, interface, signal, parameters):
        self.sent.append((destination, path, interface, signal, parameters.unpack()))
        return True


def until(condition, timeout=5.0):
    context, deadline = GLib.MainContext.default(), time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)
    return condition()


def settle(seconds=0.2):
    """Let the main loop turn for a while: a signal that is sent again would show up."""
    context, deadline = GLib.MainContext.default(), time.monotonic() + seconds
    while time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)


def test_a_new_runner_is_idle_and_knows_its_connection():
    wire = Wire()
    runner = JobRunner(wire)

    assert runner._connection is wire
    assert runner._running is False and runner._backup_running is False
    assert runner.unavailable == "" and runner.unavailable_reason == ""


def test_a_job_says_its_progress_and_its_end_on_the_bus_once_each():
    wire = Wire()
    runner = JobRunner(wire)

    def task(on_progress):
        on_progress(SimpleNamespace(path="/home/u/a.txt"))
        return True, ""

    runner.submit("job-1", task, records_backup=True)
    assert until(lambda: len(wire.sent) == 2)
    settle()

    assert wire.sent == [
        (None, PATH, INTERFACE, "Progress", ("job-1", -1.0, "/home/u/a.txt")),
        (None, PATH, INTERFACE, "BackupFinished", ("job-1", True, "")),
    ]


def test_a_destination_that_cannot_be_used_ends_the_job_with_the_text_of_its_error():
    wire = Wire()
    runner = JobRunner(wire)
    error = DestinationUnavailable("/media/disk/delta", DestinationState.FULL)

    def blocked(on_progress):
        raise error

    runner.submit("job-2", blocked, records_backup=True)
    assert until(lambda: len(wire.sent) == 1)

    assert wire.sent[0][3:] == ("BackupFinished", ("job-2", False, str(error)))


def test_a_job_that_waits_for_the_runner_to_be_idle_keeps_its_id():
    wire = Wire()
    runner = JobRunner(wire)

    runner.submit_when_idle("job-3", lambda on_progress: (True, ""))
    assert until(lambda: len(wire.sent) == 1)

    assert wire.sent[0][4][0] == "job-3"


def test_the_work_of_a_job_runs_on_a_thread_that_does_not_keep_the_daemon_alive(monkeypatch):
    made = []

    class Thread:
        def __init__(self, target=None, args=(), daemon=None):
            made.append((target, args, daemon))

        def start(self):
            made.append("started")

    monkeypatch.setattr(job_runner, "threading", SimpleNamespace(Thread=Thread, Lock=threading.Lock))
    runner = JobRunner(Wire())

    def task(on_progress):
        return True, ""

    runner.submit("job-4", task, records_backup=True)

    assert made == [(runner._work, ("job-4", task, True), True), "started"]


def test_a_job_that_did_not_succeed_is_logged_with_its_id_and_why(caplog):
    runner = JobRunner(Wire())

    with caplog.at_level(logging.WARNING, logger="delta.daemon.job_runner"):
        runner.submit("job-5", lambda on_progress: (False, "it broke"), records_backup=True)
        assert until(lambda: runner.status != "running")

    assert "job job-5 did not succeed: it broke" in [record.getMessage() for record in caplog.records]


def test_a_task_that_crashes_is_logged_with_its_job(caplog):
    runner = JobRunner(Wire())

    def crash(on_progress):
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="delta.daemon.job_runner"), pytest.raises(RuntimeError):
        runner._work("job-6", crash, True)

    assert "job job-6 crashed" in [record.getMessage() for record in caplog.records]


def test_a_callback_waits_again_if_another_job_started_before_it_could_run():
    runner = JobRunner(Wire())
    first, second, ran = threading.Event(), threading.Event(), []

    def hold(gate):
        def task(on_progress):
            gate.wait(5)
            return True, ""

        return task

    runner.submit("a", hold(first), records_backup=False)
    runner.when_idle(lambda: ran.append("callback"))  # a job is running: it waits for it
    first.set()
    while runner.status == "running":  # the first has ended; the main loop has not turned yet
        time.sleep(0.001)
    runner.submit("b", hold(second), records_backup=False)

    settle()
    assert ran == []  # another job is running: the callback has to wait for that one too

    second.set()
    assert until(lambda: ran == ["callback"])
