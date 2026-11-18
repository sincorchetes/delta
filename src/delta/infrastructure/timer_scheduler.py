"""Scheduler adapter for installs without `systemd --user` (the Flatpak): the daemon keeps the time itself."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

from delta.domain.errors import SchedulerError
from delta.domain.recurrence import Recurrence, parse
from delta.domain.schedule import Schedule

log = logging.getLogger(__name__)

# Looked at once a minute, not armed for the exact moment: a timer set for hours ahead does not count the time
# the computer sleeps, and one that is checked against the clock is right after a suspend or a change of time.
TICK_SECONDS = 60


@dataclass
class _Plan:
    """What is applied: the recurrence, the next due time, and whether a missed backup was already looked for."""

    recurrence: Recurrence
    due: datetime
    missed_checked: bool


class TimerScheduler:
    """Asks `trigger` for a backup when the schedule says so, and once on starting if one was missed.

    The missed one is what `Persistent=true` does in the systemd timer: the computer was off at the due time.
    It is looked at once, so a backup that fails is not tried again every minute.
    """

    def __init__(
        self,
        trigger: Callable[[], None],
        last_backup: Callable[[], int],
        now: Callable[[], datetime] = datetime.now,
        add_timer: Callable[[int, Callable[[], bool]], int] = GLib.timeout_add_seconds,
        remove_timer: Callable[[int], object] = GLib.source_remove,
    ) -> None:
        self._trigger = trigger
        self._last_backup = last_backup
        self._now = now
        self._add_timer = add_timer
        self._remove_timer = remove_timer
        self._plan: _Plan | None = None
        self._timer: int | None = None

    def apply(self, schedule: Schedule) -> None:
        try:
            recurrence = parse(schedule.on_calendar)
        except ValueError as err:
            raise SchedulerError(str(err)) from err
        self._plan = _Plan(recurrence, recurrence.next_after(self._now()), False)
        if self._timer is None:
            self._timer = self._add_timer(TICK_SECONDS, self._tick)

    def disable(self) -> None:
        self._plan = None
        if self._timer is not None:
            self._remove_timer(self._timer)
            self._timer = None

    def next_run(self) -> datetime | None:
        plan = self._plan
        return None if plan is None else plan.due.astimezone(timezone.utc)

    def _tick(self) -> bool:
        plan = self._plan
        if plan is None:
            return GLib.SOURCE_REMOVE
        now = self._now()
        if now >= plan.due:
            plan.due = plan.recurrence.next_after(now)
            plan.missed_checked = True
            self._fire()
        elif self._missed_while_off(plan, now):
            self._fire()
        return GLib.SOURCE_CONTINUE

    def _missed_while_off(self, plan: _Plan, now: datetime) -> bool:
        if plan.missed_checked:
            return False
        last = self._last_backup()
        if last <= 0:
            return False  # not known yet (the daemon is still asking the repository), or never backed up
        plan.missed_checked = True
        return datetime.fromtimestamp(last) < plan.recurrence.latest_up_to(now)

    def _fire(self) -> None:
        try:
            self._trigger()
        except Exception:  # noqa: BLE001 - a backup that cannot start must not stop the clock
            log.exception("the scheduled backup could not be started")
