"""Applies GSettings changes: schedule at once, services only between jobs."""

import logging
from collections.abc import Callable

from delta.application.ports import Scheduler
from delta.daemon.job_runner import JobRunner
from delta.domain.errors import SchedulerError
from delta.domain.schedule import Schedule

log = logging.getLogger(__name__)

SCHEDULE_KEYS = frozenset({"schedule", "repository-location"})
SERVICE_KEYS = frozenset(
    {
        "repository-location",
        "backup-sources",
        "excluded-paths",
        "keep-hourly",
        "keep-daily",
        "keep-weekly",
        "keep-monthly",
    }
)


class ConfigReloader:
    """Never interrupts a running job: a rebuild waits until the runner is idle."""

    def __init__(
        self,
        settings,
        jobs: JobRunner,
        rebuild: Callable[[], None],
        scheduler: Scheduler,
        has_repository: Callable[[], bool],
    ) -> None:
        self._settings = settings
        self._jobs = jobs
        self._rebuild = rebuild
        self._scheduler = scheduler
        self._has_repository = has_repository

    def start(self) -> None:
        self._settings.connect("changed", self._on_changed)
        self.apply_schedule()

    def apply_schedule(self) -> None:
        """Timers only affect future runs, so this is safe during a backup."""
        try:
            if self._has_repository():
                self._scheduler.apply(Schedule(self._settings.get_string("schedule")))
            else:
                self._scheduler.disable()
        except (SchedulerError, ValueError) as err:
            log.warning("cannot apply backup schedule: %s", err)

    def _on_changed(self, settings, key: str) -> None:
        if key in SCHEDULE_KEYS:
            self.apply_schedule()
        if key in SERVICE_KEYS:
            self._jobs.when_idle(self._rebuild)
