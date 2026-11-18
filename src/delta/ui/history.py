"""The backup history table, decided from ListSnapshots rows. No GTK, no D-Bus."""

from dataclasses import dataclass
from datetime import datetime

from delta.i18n import ngettext
from delta.ui.status import relative_time


@dataclass(frozen=True)
class HistoryRow:
    name: str
    when: str
    ago: str


def build_history(rows: list[dict], now: datetime) -> list[HistoryRow]:
    """Newest first; the date is unambiguous (ISO order), the age is the friendly part."""
    newest_first = sorted(rows, key=lambda row: row["time"], reverse=True)
    return [
        HistoryRow(
            name=row["name"],
            when=f"{datetime.fromtimestamp(row['time']):%Y-%m-%d  %H:%M}",
            ago=relative_time(row["time"], now),
        )
        for row in newest_first
    ]


def describe_count(count: int) -> str:
    return ngettext("{n} backup", "{n} backups", count).format(n=count)
