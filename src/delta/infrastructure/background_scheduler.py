"""A scheduler that first makes sure the daemon may keep running in the background (the Flatpak)."""

import logging
from datetime import datetime

from delta.application.ports import Scheduler
from delta.domain.schedule import Schedule
from delta.infrastructure.background_portal import BackgroundPortal

log = logging.getLogger(__name__)


class BackgroundScheduler:
    """Asks the portal when a schedule is first applied (never before: nothing to schedule yet), then
    leaves the timekeeping to `inner`. If the user says no, backups still follow the schedule while Delta runs."""

    def __init__(self, inner: Scheduler, portal: BackgroundPortal) -> None:
        self._inner = inner
        self._portal = portal
        self._asked = False

    def apply(self, schedule: Schedule) -> None:
        self._inner.apply(schedule)
        if not self._asked:
            self._asked = True
            self._portal.request(self._answered)

    def disable(self) -> None:
        self._inner.disable()

    def next_run(self) -> datetime | None:
        return self._inner.next_run()

    @staticmethod
    def _answered(granted: bool) -> None:
        if granted:
            log.info("Delta may run in the background and starts at login")
        else:
            log.warning("Delta may not run in the background: scheduled backups only happen while it is open")
