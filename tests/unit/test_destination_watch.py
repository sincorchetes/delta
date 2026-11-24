"""The place of the backups is looked at in the background: asking for its state never waits for the drive."""

import pytest

from delta.daemon.destination_watch import DestinationWatch
from delta.domain.destination import DestinationState
from delta.domain.repository import Repository

REPO = Repository("/media/disk/delta")


class Probe:
    def __init__(self, answer=DestinationState.MISSING):
        self.answer, self.asked = answer, []

    def state(self, repo, out_of_space=False):
        self.asked.append(repo)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class Later:
    """Holds the work back, as a thread that has not run yet."""

    def __init__(self):
        self.work = []

    def __call__(self, work):
        self.work.append(work)

    def run(self):
        work, self.work = self.work, []
        for item in work:
            item()


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def parts():
    return Probe(), Later(), Clock()


def watch_of(parts, repository=lambda: REPO):
    probe, later, clock = parts
    return DestinationWatch(probe, repository, max_age=10.0, clock=clock, spawn=later)


def test_nothing_is_known_until_the_first_look_has_run(parts):
    watch = watch_of(parts)

    assert watch.state() is DestinationState.AVAILABLE and parts[0].asked == []

    parts[1].run()

    assert watch.state() is DestinationState.MISSING and parts[0].asked == [REPO]


def test_a_look_that_is_under_way_is_not_started_again(parts):
    watch = watch_of(parts)

    watch.state()
    watch.state()
    watch.refresh()

    assert len(parts[1].work) == 1


def test_what_is_known_is_kept_for_a_while_and_then_looked_at_again(parts):
    probe, later, clock = parts
    watch = watch_of(parts)
    watch.state()
    later.run()

    clock.now = 9.9
    watch.state()
    assert later.work == []

    clock.now = 10.0
    probe.answer = DestinationState.AVAILABLE
    assert watch.state() is DestinationState.MISSING  # the old answer, at once
    later.run()
    assert watch.state() is DestinationState.AVAILABLE


def test_a_look_can_be_asked_for_before_it_is_stale(parts):
    watch = watch_of(parts)
    watch.state()
    parts[1].run()

    watch.refresh()
    parts[0].answer = DestinationState.FULL
    parts[1].run()

    assert watch.state() is DestinationState.FULL


def test_without_a_repository_there_is_nothing_to_look_at(parts):
    watch = watch_of(parts, repository=lambda: None)
    watch.refresh()
    parts[1].run()

    assert watch.state() is DestinationState.AVAILABLE and parts[0].asked == []


def test_a_probe_that_breaks_is_logged_and_counts_as_nothing_wrong(parts, caplog):
    parts[0].answer = RuntimeError("boom")
    watch = watch_of(parts)
    watch.refresh()

    with caplog.at_level("WARNING", logger="delta.daemon.destination_watch"):
        parts[1].run()

    assert watch.state() is DestinationState.AVAILABLE
    assert [record.getMessage() for record in caplog.records] == ["cannot look at the place of the backups: boom"]
    watch.refresh()  # it can look again afterwards
    assert len(parts[1].work) == 1


def test_by_default_the_look_runs_on_a_thread_of_its_own():
    probe = Probe(DestinationState.EMPTY)
    watch = DestinationWatch(probe, lambda: REPO)
    watch.refresh()

    import time

    deadline = time.monotonic() + 5
    while not probe.asked and time.monotonic() < deadline:
        time.sleep(0.01)

    assert probe.asked == [REPO]
