import pytest

from delta.domain.errors import SchedulerError
from delta.domain.schedule import Schedule
from delta.infrastructure.systemd_scheduler import SystemdScheduler, run_systemctl


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)


@pytest.fixture
def world(tmp_path):
    recorder = Recorder()
    scheduler = SystemdScheduler(str(tmp_path), recorder)
    dropin = tmp_path / "systemd" / "user" / "delta.timer.d" / "schedule.conf"
    return scheduler, recorder, dropin


@pytest.mark.parametrize("expr", ["hourly", "daily", "*-*-* 02:30:00", "Mon,Fri *-*-* 10:00", "*:0/15"])
def test_valid_expressions(expr):
    assert Schedule(expr).on_calendar == expr


@pytest.mark.parametrize(
    "expr", ["", "   ", "hourly\nExecStart=/bin/sh", "daily\n[Service]", "a=b", "x;y", "$(id)"]
)
def test_unsafe_expressions_are_rejected(expr):
    with pytest.raises(ValueError):
        Schedule(expr)


def test_apply_writes_dropin_and_enables_timer(world):
    scheduler, recorder, dropin = world

    scheduler.apply(Schedule("daily"))

    assert dropin.read_text() == "[Timer]\nOnCalendar=\nOnCalendar=daily\n"
    assert recorder.calls == [["daemon-reload"], ["enable", "--now", "delta.timer"]]


def test_apply_again_replaces_previous_schedule(world):
    scheduler, _, dropin = world
    scheduler.apply(Schedule("daily"))
    scheduler.apply(Schedule("hourly"))
    assert dropin.read_text().endswith("OnCalendar=hourly\n")
    assert not dropin.with_suffix(".tmp").exists()


def test_disable_stops_timer_and_removes_dropin(world):
    scheduler, recorder, dropin = world
    scheduler.apply(Schedule("daily"))
    recorder.calls.clear()

    scheduler.disable()

    assert not dropin.exists()
    assert recorder.calls == [["disable", "--now", "delta.timer"], ["daemon-reload"]]


def test_disable_without_dropin_is_harmless(world):
    scheduler, _, _ = world
    scheduler.disable()


def test_failing_systemctl_raises_scheduler_error():
    with pytest.raises(SchedulerError):
        run_systemctl(["definitely-not-a-verb"])


def _scheduler_reading(text=None, error=None):
    asked = []

    def reader(args):
        asked.append(args)
        if error:
            raise error
        return text

    return SystemdScheduler("/unused", lambda args: None, reader), asked


def test_the_next_run_is_read_from_the_timer_as_a_unix_timestamp():
    scheduler, asked = _scheduler_reading("@1731264000\n")
    moment = scheduler.next_run()
    assert moment is not None and int(moment.timestamp()) == 1731264000
    assert asked == [
        ["show", "--timestamp=unix", "-p", "NextElapseUSecRealtime", "--value", "delta.timer"]
    ]


@pytest.mark.parametrize("text", ["", "n/a", "@0", "@", "Tue 2026-11-10 19:00:00 CET", "@12x"])
def test_an_unreadable_or_absent_next_run_is_none(text):
    assert _scheduler_reading(text)[0].next_run() is None


def test_a_failing_systemctl_means_no_known_next_run():
    scheduler, _ = _scheduler_reading(error=SchedulerError("no user bus"))
    assert scheduler.next_run() is None
