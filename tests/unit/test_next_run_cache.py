from datetime import datetime, timezone

from delta.daemon.next_run import NextRunCache

MOMENT = datetime(2026, 11, 10, 19, 0, tzinfo=timezone.utc)


class Scheduler:
    def __init__(self, moment=MOMENT, error=None):
        self.moment, self.error, self.calls = moment, error, 0

    def next_run(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.moment


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def cache_for(scheduler, clock=None, deferred=None):
    """`deferred` collects the refresh jobs instead of running them, to see the in-between state."""
    spawn = deferred.append if deferred is not None else (lambda work: work())
    return NextRunCache(scheduler, max_age=60, clock=clock or Clock(), spawn=spawn)


def test_the_first_read_answers_at_once_with_unknown_and_refreshes_behind_it():
    deferred = []
    cache = cache_for(Scheduler(), deferred=deferred)
    assert cache.value() == 0
    deferred.pop()()
    assert cache.value() == int(MOMENT.timestamp())


def test_a_fresh_value_is_reused_and_a_stale_one_refreshed():
    scheduler, clock = Scheduler(), Clock()
    cache = cache_for(scheduler, clock)
    cache.value()
    cache.value()
    assert scheduler.calls == 1
    clock.now += 61
    cache.value()
    assert scheduler.calls == 2


def test_reads_during_a_refresh_do_not_start_another():
    scheduler, deferred = Scheduler(), []
    cache = cache_for(scheduler, deferred=deferred)
    cache.value()
    cache.value()
    cache.value()
    assert len(deferred) == 1 and scheduler.calls == 0


def test_no_next_run_is_zero():
    cache = cache_for(Scheduler(moment=None))
    cache.value()
    assert cache.value() == 0


def test_a_broken_scheduler_is_zero_and_does_not_hammer_systemd():
    scheduler = Scheduler(error=RuntimeError("boom"))
    cache = cache_for(scheduler)
    assert cache.value() == 0
    assert cache.value() == 0
    assert scheduler.calls == 1
