"""The previous versions of one file, decided from ListVersions rows. No GTK, no D-Bus."""

from dataclasses import dataclass
from datetime import datetime

from delta.i18n import _
from delta.ui.status import relative_time

UNITS = ("kB", "MB", "GB", "TB")


@dataclass(frozen=True)
class VersionRow:
    snapshot: str  # what the daemon needs to restore this version
    modified: str  # when the file was saved, which is how people recognise a version
    backed_up: str  # when Delta copied it, and how big it was
    size: int = 0
    is_dir: bool = False


def step_index(current: int | None, delta: int, count: int) -> int | None:
    """The index `delta` places from `current` among `count`, or None when there is nowhere to go
    (nothing is chosen, or it would run past either end)."""
    if current is None:
        return None
    target = current + delta
    return target if 0 <= target < count else None


def format_size(size: int) -> str:
    """Decimal units, as GNOME shows them (1 kB = 1000 bytes)."""
    if size < 1000:
        return _("{n} bytes").format(n=size)
    value = float(size)
    for unit in UNITS[:-1]:
        value /= 1000
        if value < 1000:
            return f"{value:.1f} {unit}"
    return f"{value / 1000:.1f} {UNITS[-1]}"  # the biggest unit takes whatever is left


def build_versions(rows: list[dict], now: datetime) -> list[VersionRow]:
    """Newest first, by the moment the file was saved."""
    newest = sorted(rows, key=lambda row: row["mtime"], reverse=True)
    return [
        VersionRow(
            snapshot=row["name"],
            modified=f"{datetime.fromtimestamp(row['mtime']):%Y-%m-%d  %H:%M}",
            backed_up=_("Backed up {when} · {size}").format(
                when=relative_time(row["time"], now), size=format_size(row["size"])
            ),
            size=row["size"],
            is_dir=row.get("is_dir", False),
        )
        for row in newest
    ]
