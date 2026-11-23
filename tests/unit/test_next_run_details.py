"""The cache of the next scheduled backup: when it goes stale, what it keeps and the thread it works on."""

from datetime import datetime
from types import SimpleNamespace

from delta.daemon import next_run
from delta.daemon.next_run import NextRunCache


class Scheduler:
    def __init__(self, moment):
        self.moment = moment

    def next_run(self):
        return self.moment


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_the_work_runs_on_a_thread_that_does_not_keep_the_daemon_alive(monkeypatch):
    made = []

    class Thread:
        def __init__(self, target=None, daemon=None):
            made.append((target, daemon))

        def start(self):
            made.append("started")

    monkeypatch.setattr(next_run, "threading", SimpleNamespace(Thread=Thread))

    def work():
        pass

    next_run._in_background(work)

    assert made == [(work, True), "started"]


def test_a_cache_is_not_refreshing_until_it_is_asked_and_not_after_it_is_done():
    spawned = []
    cache = NextRunCache(Scheduler(datetime(2026, 1, 1)), 60.0, Clock(), spawned.append)
    assert cache._refreshing is False

    cache.value()
    assert cache._refreshing is True

    spawned.pop()()
    assert cache._refreshing is False


def test_the_value_is_stale_exactly_when_it_is_as_old_as_the_limit():
    clock, spawned = Clock(), []
    cache = NextRunCache(Scheduler(datetime(2026, 1, 1)), 60.0, clock, spawned.append)
    cache.value()
    spawned.pop()()  # checked at 100

    clock.now = 159.0
    cache.value()
    assert spawned == []

    clock.now = 160.0
    cache.value()
    assert len(spawned) == 1


def test_a_schedule_with_no_next_moment_is_zero_and_one_with_it_is_its_epoch():
    spawned = []
    nothing = NextRunCache(Scheduler(None), 60.0, Clock(), spawned.append)
    nothing.value()
    spawned.pop()()
    assert nothing.value() == 0

    moment = datetime(2026, 1, 1, 12, 0, 0)
    some = NextRunCache(Scheduler(moment), 60.0, Clock(), spawned.append)
    some.value()
    spawned.pop()()
    assert some.value() == int(moment.timestamp())
