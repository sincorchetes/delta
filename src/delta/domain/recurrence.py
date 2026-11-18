"""When a schedule fires, worked out without systemd: the part of a calendar expression Delta offers.

systemd does this for the native install. Where there is no `systemd --user` (the Flatpak), the daemon keeps its
own time, so it needs to know when the next backup is due. Local time, without time zones, as systemd.time(7) reads it.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

SEARCH_DAYS = 400  # more than a year: far enough to find the next day of any schedule that has one
WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass(frozen=True)
class Recurrence:
    """Every day that matches (a month, a day of the month, a weekday), at `hour`:`minute`:`second`.

    `None` means any; an `hour` of None is every hour of the day.
    """

    minute: int = 0
    second: int = 0
    hour: int | None = None
    weekdays: frozenset[int] | None = None  # Monday is 0
    months: frozenset[int] | None = None
    day: int | None = None

    def _matches_day(self, moment: datetime) -> bool:
        return (
            (self.weekdays is None or moment.weekday() in self.weekdays)
            and (self.months is None or moment.month in self.months)
            and (self.day is None or moment.day == self.day)
        )

    def _times_of(self, day: datetime) -> list[datetime]:
        hours = range(24) if self.hour is None else (self.hour,)
        return [day.replace(hour=h, minute=self.minute, second=self.second) for h in hours]

    def next_after(self, moment: datetime) -> datetime:
        """The first moment strictly after `moment`."""
        midnight = datetime.combine(moment.date(), time.min)
        for offset in range(SEARCH_DAYS):
            day = midnight + timedelta(days=offset)
            if self._matches_day(day):
                for candidate in self._times_of(day):
                    if candidate > moment:
                        return candidate
        raise ValueError("this schedule never fires")

    def latest_up_to(self, moment: datetime) -> datetime:
        """The last moment at or before `moment`: when the schedule last should have fired."""
        midnight = datetime.combine(moment.date(), time.min)
        for offset in range(SEARCH_DAYS):
            day = midnight - timedelta(days=offset)
            if self._matches_day(day):
                for candidate in reversed(self._times_of(day)):
                    if candidate <= moment:
                        return candidate
        raise ValueError("this schedule never fires")


YEARLY = Recurrence(hour=0, day=1, months=frozenset({1}))
SHORTCUTS = {
    "hourly": Recurrence(),
    "daily": Recurrence(hour=0),
    "weekly": Recurrence(hour=0, weekdays=frozenset({0})),
    "monthly": Recurrence(hour=0, day=1),
    "quarterly": Recurrence(hour=0, day=1, months=frozenset({1, 4, 7, 10})),
    "semiannually": Recurrence(hour=0, day=1, months=frozenset({1, 7})),
    "yearly": YEARLY,
    "annually": YEARLY,
}


def _weekday_list(text: str) -> frozenset[int]:
    """`Mon`, `Mon,Fri` or `Mon..Fri` (a range may wrap: `Fri..Mon`)."""
    chosen: set[int] = set()
    for part in text.lower().split(","):
        first, dots, last = part.partition("..")
        if first not in WEEKDAYS or (dots and last not in WEEKDAYS):
            raise ValueError(f"unknown weekday in {text!r}")
        start, end = WEEKDAYS[first], WEEKDAYS[last] if dots else WEEKDAYS[first]
        chosen.update(range(start, end + 1) if start <= end else [*range(start, 7), *range(end + 1)])
    return frozenset(chosen)


def _time_of_day(text: str) -> tuple[int, int, int]:
    pieces = text.split(":")
    if len(pieces) not in (2, 3) or not all(p.isdigit() and len(p) == 2 for p in pieces):
        raise ValueError(f"not a time of day: {text!r}")
    hour, minute, second = int(pieces[0]), int(pieces[1]), int(pieces[2]) if len(pieces) == 3 else 0
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError(f"not a time of day: {text!r}")
    return hour, minute, second


def parse(expression: str) -> Recurrence:
    """The shortcuts (hourly, daily, weekly, monthly, quarterly, semiannually, yearly) and
    `[weekdays] *-*-* HH:MM[:SS]`. Anything else is something only systemd understands."""
    text = expression.strip()
    shortcut = SHORTCUTS.get(text.lower())
    if shortcut is not None:
        return shortcut
    parts = text.split()
    weekdays = _weekday_list(parts.pop(0)) if len(parts) == 3 else None
    if len(parts) != 2 or parts[0] != "*-*-*":
        raise ValueError(f"only the schedules Delta offers can be followed here: {expression!r}")
    hour, minute, second = _time_of_day(parts[1])
    return Recurrence(minute=minute, second=second, hour=hour, weekdays=weekdays)
