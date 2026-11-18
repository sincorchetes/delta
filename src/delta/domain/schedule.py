"""When automatic backups run, as a systemd.time(7) calendar expression."""

import re
from dataclasses import dataclass

# Conservative whitelist: the value ends up in a unit file, so no newlines,
# '=' or '[' (which could inject other directives or sections).
_ALLOWED = re.compile(r"[A-Za-z0-9 ,.*:/~+-]+")


@dataclass(frozen=True)
class Schedule:
    on_calendar: str = "hourly"

    def __post_init__(self) -> None:
        if not self.on_calendar.strip() or not _ALLOWED.fullmatch(self.on_calendar):
            raise ValueError(f"invalid calendar expression: {self.on_calendar!r}")
