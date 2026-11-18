"""A borg that one SIGINT does not stop (it is in the middle of a large file) gets a second one.

A script stands in for borg: it ignores the first SIGINT and quits with 130 at the second, which
is what borg 1.4.5 was seen to do (scripts/verify_mount_vs_backup.sh).
"""

import sys
import threading
import time

from delta.domain.errors import BackupInterrupted
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import INSIST_AFTER, BorgRunner

REPO = Repository("/r")


def wait_until(condition, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not condition():
        time.sleep(0.01)
    return condition()

STUBBORN = """#!{python}
import pathlib, signal, sys, time

hits = []


def on_interrupt(*_):
    hits.append(1)
    if len(hits) == 2:
        sys.exit(130)


signal.signal(signal.SIGINT, on_interrupt)
pathlib.Path(sys.argv[1]).write_text("ready")
while True:
    time.sleep(0.05)
"""


class Stubborn:
    """The stand-in running on its own thread, started once it is ready to count signals."""

    def __init__(self, tmp_path, insist_after):
        script = tmp_path / "stubborn-borg"
        script.write_text(STUBBORN.format(python=sys.executable))
        script.chmod(0o755)
        self.ready = tmp_path / "ready"
        self.runner = BorgRunner(binary=str(script), insist_after=insist_after)
        self.outcome = {}
        self.thread = threading.Thread(target=self._work, daemon=True)
        self.thread.start()
        assert wait_until(self.ready.exists), "the stand-in never started"

    def _work(self):
        try:
            self.runner._run(["borg", str(self.ready)], REPO)
            self.outcome["ended"] = "normally"
        except BackupInterrupted:
            self.outcome["ended"] = "interrupted"

    def end(self):
        self.runner._insist(list(self.runner._running))
        self.thread.join(5)


def test_the_wait_before_insisting_is_a_few_seconds():
    assert INSIST_AFTER == 5.0
    assert BorgRunner()._insist_after == INSIST_AFTER


def test_one_signal_alone_does_not_stop_it_and_the_second_does(tmp_path):
    borg = Stubborn(tmp_path, insist_after=3600)
    try:
        borg.runner.interrupt()
        borg.thread.join(0.3)
        assert borg.thread.is_alive() and len(borg.runner._running) == 1

        borg.runner._insist(list(borg.runner._running))
        borg.thread.join(5)

        assert borg.outcome == {"ended": "interrupted"}
    finally:
        borg.end()


def test_interrupt_insists_by_itself_after_the_wait(tmp_path):
    borg = Stubborn(tmp_path, insist_after=0.05)
    try:
        borg.runner.interrupt()
        borg.thread.join(5)

        assert borg.outcome == {"ended": "interrupted"}
        assert borg.runner._running == set() and borg.runner._interrupted == set()
    finally:
        borg.end()


def test_insisting_leaves_alone_what_already_ended(tmp_path):
    borg = Stubborn(tmp_path, insist_after=3600)
    gone = list(borg.runner._running)
    borg.runner.interrupt()
    borg.end()
    assert borg.outcome == {"ended": "interrupted"}

    borg.runner._insist(gone)

    assert borg.runner._running == set()
