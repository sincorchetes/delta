"""The scheduler that keeps time inside the daemon: when it fires, what it does at start-up, and that it never loops."""

import logging
import time
from datetime import datetime, timedelta, timezone

import pytest
from gi.repository import GLib

from delta.domain.errors import SchedulerError
from delta.domain.schedule import Schedule
from delta.infrastructure.timer_scheduler import TICK_SECONDS, TimerScheduler

START = datetime(2026, 11, 18, 10, 30, 0)


class World:
    """A clock the test moves, and the timer calls and triggers the scheduler makes."""

    def __init__(self, last_backup=0):
        self.now, self.last_backup = START, last_backup
        self.fired, self.timers, self.removed = [], [], []
        self.scheduler = TimerScheduler(
            lambda: self.fired.append(self.now),
            lambda: self.last_backup,
            now=lambda: self.now,
            add_timer=self.add_timer,
            remove_timer=self.removed.append,
        )

    def add_timer(self, seconds, callback):
        self.timers.append((seconds, callback))
        return len(self.timers)

    def tick(self, at=None):
        self.now = at or self.now
        return self.timers[-1][1]()


@pytest.fixture
def world():
    return World()


def test_it_looks_at_the_clock_every_minute_once_a_schedule_is_applied(world):
    world.scheduler.apply(Schedule("hourly"))
    world.scheduler.apply(Schedule("daily"))  # a new schedule reuses the timer

    assert [seconds for seconds, _ in world.timers] == [TICK_SECONDS] and TICK_SECONDS == 60


def test_the_next_run_is_the_next_time_the_schedule_names(world):
    world.scheduler.apply(Schedule("hourly"))

    expected = datetime(2026, 11, 18, 11, 0).astimezone(timezone.utc)
    assert world.scheduler.next_run() == expected and world.scheduler.next_run().tzinfo is not None


def test_the_next_run_is_always_given_in_utc_whatever_the_time_zone_of_the_computer(world, monkeypatch):
    with monkeypatch.context() as local:
        local.setenv("TZ", "XYZ-2")  # two hours ahead of UTC
        time.tzset()
        try:
            world.scheduler.apply(Schedule("hourly"))
            next_run = world.scheduler.next_run()
        finally:
            local.undo()
            time.tzset()

    assert next_run == datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc)
    assert next_run.utcoffset() == timedelta(0)


def test_with_nothing_applied_there_is_no_next_run(world):
    assert world.scheduler.next_run() is None


def test_nothing_happens_before_the_due_time(world):
    world.scheduler.apply(Schedule("hourly"))

    assert world.tick(datetime(2026, 11, 18, 10, 59, 59)) is GLib.SOURCE_CONTINUE
    assert world.fired == []


def test_at_the_due_time_it_asks_for_a_backup_and_waits_for_the_next(world):
    world.scheduler.apply(Schedule("hourly"))

    world.tick(datetime(2026, 11, 18, 11, 0, 5))
    world.tick(datetime(2026, 11, 18, 11, 30))

    assert world.fired == [datetime(2026, 11, 18, 11, 0, 5)]
    assert world.scheduler.next_run() == datetime(2026, 11, 18, 12, 0).astimezone(timezone.utc)


def test_the_very_moment_of_the_due_time_already_fires(world):
    world.scheduler.apply(Schedule("hourly"))

    world.tick(datetime(2026, 11, 18, 11, 0, 0))

    assert len(world.fired) == 1


def test_a_backup_made_because_it_was_due_is_not_asked_for_again_as_a_missed_one():
    world = World(last_backup=int(datetime(2026, 11, 18, 7, 15).timestamp()))  # the repository still says the old one
    world.scheduler.apply(Schedule("hourly"))

    world.tick(datetime(2026, 11, 18, 11, 0, 5))
    world.tick(datetime(2026, 11, 18, 11, 30))

    assert len(world.fired) == 1


def test_after_a_sleep_a_due_time_that_passed_fires_once_not_once_for_each_missed(world):
    world.scheduler.apply(Schedule("hourly"))

    world.tick(datetime(2026, 11, 18, 15, 20))  # the computer slept for five hours

    assert len(world.fired) == 1
    assert world.scheduler.next_run() == datetime(2026, 11, 18, 16, 0).astimezone(timezone.utc)


def test_a_backup_missed_while_the_computer_was_off_is_made_on_starting_but_once():
    world = World(last_backup=int(datetime(2026, 11, 18, 7, 15).timestamp()))  # the last one was before 10:00
    world.scheduler.apply(Schedule("hourly"))

    world.tick()
    world.tick()  # still not backed up (it failed, say): not asked again

    assert len(world.fired) == 1


def test_no_backup_is_made_on_starting_when_the_last_one_was_after_the_last_due_time():
    world = World(last_backup=int(datetime(2026, 11, 18, 10, 5).timestamp()))
    world.scheduler.apply(Schedule("hourly"))

    world.tick()

    assert world.fired == []


def test_a_backup_made_exactly_at_the_last_due_time_is_not_a_missed_one():
    world = World(last_backup=int(datetime(2026, 11, 18, 10, 0).timestamp()))
    world.scheduler.apply(Schedule("hourly"))

    world.tick()

    assert world.fired == []


def test_a_backup_one_second_after_the_epoch_is_a_known_and_very_old_one():
    world = World(last_backup=1)
    world.scheduler.apply(Schedule("hourly"))

    world.tick()

    assert len(world.fired) == 1


def test_until_the_last_backup_is_known_nothing_is_decided_and_it_is_asked_again_later():
    world = World(last_backup=0)
    world.scheduler.apply(Schedule("hourly"))

    world.tick()
    world.last_backup = int(datetime(2026, 11, 18, 7, 15).timestamp())  # the repository answered
    world.tick()

    assert len(world.fired) == 1


def test_a_new_schedule_looks_again_for_what_it_would_have_missed(world):
    world.last_backup = int(datetime(2026, 11, 18, 7, 15).timestamp())
    world.scheduler.apply(Schedule("hourly"))
    world.tick()
    assert len(world.fired) == 1

    world.scheduler.apply(Schedule("daily"))  # its last due time was midnight, before that backup: nothing missed
    world.tick()
    assert len(world.fired) == 1

    world.scheduler.apply(Schedule("*-*-* 08:00"))  # this one was due at 08:00, after it: missed
    world.tick()
    assert len(world.fired) == 2


def test_a_backup_that_could_not_be_started_is_logged_and_the_clock_goes_on(world, caplog):
    def refuse():
        raise RuntimeError("no repository")

    world.scheduler._trigger = refuse
    world.scheduler.apply(Schedule("hourly"))

    with caplog.at_level(logging.ERROR):
        result = world.tick(datetime(2026, 11, 18, 11, 0, 1))

    assert result is GLib.SOURCE_CONTINUE
    assert [record.getMessage() for record in caplog.records] == ["the scheduled backup could not be started"]
    assert world.scheduler.next_run() == datetime(2026, 11, 18, 12, 0).astimezone(timezone.utc)


def test_disabling_stops_the_clock_and_forgets_the_next_run(world):
    world.scheduler.apply(Schedule("hourly"))

    world.scheduler.disable()

    assert world.removed == [1] and world.scheduler.next_run() is None


def test_disabling_without_a_schedule_is_harmless(world):
    world.scheduler.disable()

    assert world.removed == []


def test_a_timer_that_fires_after_being_disabled_ends_itself(world):
    world.scheduler.apply(Schedule("hourly"))
    callback = world.timers[-1][1]
    world.scheduler.disable()

    assert callback() is GLib.SOURCE_REMOVE and world.fired == []
    world.scheduler.apply(Schedule("hourly"))
    assert len(world.timers) == 2  # and a later schedule starts a new one


def test_a_schedule_only_systemd_understands_is_refused_with_a_scheduler_error(world):
    with pytest.raises(SchedulerError, match="only the schedules Delta offers"):
        world.scheduler.apply(Schedule("*-*-01 02:00"))

    assert world.timers == [] and world.scheduler.next_run() is None


def test_by_default_it_uses_the_real_clock_and_glib_timers():
    scheduler = TimerScheduler(lambda: None, lambda: 0)

    assert scheduler._now == datetime.now and scheduler._add_timer == GLib.timeout_add_seconds
    assert scheduler._remove_timer == GLib.source_remove
