"""Stopping borg on shutdown while reads and a backup overlap. `sleep` stands in for borg."""

import shutil
import threading
import time

import pytest

from delta.domain.errors import BackupInterrupted, EngineError
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("sleep") is None, reason="no sleep binary")

REPO = Repository("/r")


def wait_until(condition, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not condition():
        time.sleep(0.01)
    return condition()


class Running:
    """A long-running 'backup' on its own thread, whose outcome the test can read."""

    def __init__(self, runner, seconds="30"):
        self.runner, self.outcome = runner, {}
        self.thread = threading.Thread(target=self._work, args=(seconds,), daemon=True)

    def _work(self, seconds):
        try:
            self.runner._run(["borg", seconds], REPO)
            self.outcome["ended"] = "normally"
        except BackupInterrupted:
            self.outcome["ended"] = "interrupted"
        except EngineError as err:
            self.outcome["ended"] = f"failed: {err}"

    def start(self, expected=1):
        """Start, and wait until `expected` borg processes (this one included) are running."""
        self.thread.start()
        assert wait_until(lambda: len(self.runner._running) >= expected), "the process never started"
        return self

    def finish(self):
        self.runner.interrupt()  # never leave a sleeper behind, whatever the test found
        self.thread.join(5)


def test_interrupting_stops_a_running_borg_and_says_it_was_a_stop_not_an_error():
    runner = BorgRunner(binary="sleep")
    backup = Running(runner).start()
    try:
        runner.interrupt()
        backup.thread.join(5)
        assert backup.outcome == {"ended": "interrupted"}
    finally:
        backup.finish()


def test_a_read_that_ends_meanwhile_does_not_make_the_backup_unreachable():
    """The bug: one tracked process, so a read finishing cleared the backup from the list."""
    runner = BorgRunner(binary="sleep")
    backup = Running(runner).start()
    try:
        runner._run(["borg", "0"], REPO)  # a version listing, say, that starts and ends during the backup
        assert len(runner._running) == 1  # the backup is still tracked

        runner.interrupt()
        backup.thread.join(5)

        assert backup.outcome == {"ended": "interrupted"}
    finally:
        backup.finish()


def test_a_read_that_starts_after_the_backup_does_not_hide_it_either():
    runner = BorgRunner(binary="sleep")
    backup = Running(runner).start()
    reader = Running(runner, seconds="30").start(expected=2)  # a second long process, beside the first
    try:
        assert len(runner._running) == 2

        runner.interrupt()
        backup.thread.join(5)
        reader.thread.join(5)

        assert backup.outcome == {"ended": "interrupted"} and reader.outcome == {"ended": "interrupted"}
    finally:
        backup.finish()
        reader.finish()


def test_what_ended_is_forgotten_so_nothing_piles_up():
    runner = BorgRunner(binary="sleep")
    for _ in range(5):
        runner._run(["borg", "0"], REPO)
    assert runner._running == set() and runner._interrupted == set()


def test_interrupting_with_nothing_running_is_harmless():
    BorgRunner(binary="sleep").interrupt()


def test_a_process_that_fails_on_its_own_is_not_taken_for_an_interruption():
    runner = BorgRunner(binary="false")  # exits 1 at once
    with pytest.raises(EngineError) as raised:
        runner._run(["borg"], REPO)
    assert not isinstance(raised.value, BackupInterrupted)
    assert runner._running == set()


def test_an_interruption_does_not_leak_into_the_next_run():
    runner = BorgRunner(binary="sleep")
    first = Running(runner).start()
    try:
        runner.interrupt()
        first.thread.join(5)
    finally:
        first.finish()

    runner._run(["borg", "0"], REPO)  # an ordinary run afterwards ends normally, not as a stop
    assert runner._interrupted == set()
