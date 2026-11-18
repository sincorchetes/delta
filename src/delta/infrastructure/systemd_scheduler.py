"""Scheduler adapter: a drop-in for the user-level delta.timer unit."""

import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from delta.domain.errors import SchedulerError
from delta.domain.schedule import Schedule

TIMER_UNIT = "delta.timer"
DROPIN_NAME = "schedule.conf"

Systemctl = Callable[[list[str]], None]


def render_dropin(schedule: Schedule) -> str:
    """Empty `OnCalendar=` first resets the value set by the base unit."""
    return f"[Timer]\nOnCalendar=\nOnCalendar={schedule.on_calendar}\n"


Reader = Callable[[list[str]], str]


def read_systemctl(args: list[str]) -> str:
    try:
        process = Gio.Subprocess.new(
            ["systemctl", "--user", *args],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        )
        _, stdout, stderr = process.communicate_utf8(None, None)
    except GLib.Error as err:
        raise SchedulerError(f"cannot run systemctl: {err.message}") from err
    if not process.get_successful():
        raise SchedulerError((stderr or "").strip() or f"systemctl {' '.join(args)} failed")
    return stdout or ""


def run_systemctl(args: list[str]) -> None:
    read_systemctl(args)


def parse_unix_timestamp(text: str) -> datetime | None:
    """`systemctl --timestamp=unix` prints `@1731264000`; anything else means "no next run"."""
    text = text.strip()
    if not text.startswith("@") or not text[1:].isdigit() or int(text[1:]) == 0:
        return None
    return datetime.fromtimestamp(int(text[1:]), timezone.utc)


class SystemdScheduler:
    def __init__(
        self,
        config_home: str | None = None,
        systemctl: Systemctl = run_systemctl,
        reader: Reader = read_systemctl,
    ) -> None:
        base = config_home or os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        self._dropin = Path(base) / "systemd" / "user" / f"{TIMER_UNIT}.d" / DROPIN_NAME
        self._systemctl = systemctl
        self._reader = reader

    def next_run(self) -> datetime | None:
        try:
            text = self._reader(
                ["show", "--timestamp=unix", "-p", "NextElapseUSecRealtime", "--value", TIMER_UNIT]
            )
        except SchedulerError:
            return None
        return parse_unix_timestamp(text)

    def apply(self, schedule: Schedule) -> None:
        self._dropin.parent.mkdir(parents=True, exist_ok=True)
        partial = self._dropin.with_suffix(".tmp")
        partial.write_text(render_dropin(schedule))
        partial.replace(self._dropin)
        self._systemctl(["daemon-reload"])
        self._systemctl(["enable", "--now", TIMER_UNIT])

    def disable(self) -> None:
        self._systemctl(["disable", "--now", TIMER_UNIT])
        self._dropin.unlink(missing_ok=True)
        self._systemctl(["daemon-reload"])
