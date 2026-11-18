from delta.daemon.config_reloader import ConfigReloader
from delta.domain.errors import SchedulerError
from delta.domain.schedule import Schedule


class FakeSettings:
    def __init__(self, schedule="daily"):
        self.values = {"schedule": schedule}
        self.handler = None

    def connect(self, signal, handler):
        assert signal == "changed"
        self.handler = handler

    def get_string(self, key):
        return self.values[key]

    def change(self, key):
        self.handler(self, key)


class FakeScheduler:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def apply(self, schedule):
        if self.fail:
            raise SchedulerError("no systemd")
        self.calls.append(("apply", schedule))

    def disable(self):
        self.calls.append(("disable",))


class FakeJobs:
    def __init__(self):
        self.deferred = []

    def when_idle(self, callback):
        self.deferred.append(callback)


def make(has_repository=True, schedule="daily", fail=False):
    settings, scheduler, jobs = FakeSettings(schedule), FakeScheduler(fail), FakeJobs()
    rebuild = lambda: None  # noqa: E731
    reloader = ConfigReloader(settings, jobs, rebuild, scheduler, lambda: has_repository)
    reloader.start()
    return settings, scheduler, jobs, rebuild


def test_start_applies_schedule_when_repository_configured():
    _, scheduler, _, _ = make()
    assert scheduler.calls == [("apply", Schedule("daily"))]


def test_start_disables_timer_without_repository():
    _, scheduler, _, _ = make(has_repository=False)
    assert scheduler.calls == [("disable",)]


def test_schedule_change_applies_timer_without_rebuilding_services():
    settings, scheduler, jobs, _ = make()
    settings.values["schedule"] = "*-*-* 03:00:00"

    settings.change("schedule")

    assert scheduler.calls[-1] == ("apply", Schedule("*-*-* 03:00:00"))
    assert jobs.deferred == []


def test_repository_change_defers_rebuild_to_idle_and_updates_timer():
    settings, scheduler, jobs, rebuild = make()

    settings.change("repository-location")

    assert jobs.deferred == [rebuild]
    assert len(scheduler.calls) == 2


def test_retention_change_defers_rebuild_only():
    settings, scheduler, jobs, rebuild = make()

    settings.change("keep-daily")

    assert jobs.deferred == [rebuild]
    assert len(scheduler.calls) == 1


def test_changing_the_backup_folders_defers_a_rebuild_only():
    settings, scheduler, jobs, rebuild = make()

    settings.change("backup-sources")

    assert jobs.deferred == [rebuild]
    assert len(scheduler.calls) == 1


def test_unrelated_key_does_nothing():
    settings, scheduler, jobs, _ = make()
    settings.change("something-else")
    assert jobs.deferred == [] and len(scheduler.calls) == 1


def test_scheduler_failure_does_not_crash_the_daemon():
    settings, _, jobs, rebuild = make(fail=True)
    settings.change("repository-location")
    assert jobs.deferred == [rebuild]


def test_invalid_schedule_value_is_ignored():
    settings, scheduler, _, _ = make(schedule="daily\nExecStart=/bin/sh")
    assert scheduler.calls == []
