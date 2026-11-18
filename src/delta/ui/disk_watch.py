"""Follow one folder on disk and say when something in it changed, once per burst of changes."""

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


class DiskWatch:
    """A restore writes several things in a row: they arrive as one call to `on_change`."""

    def __init__(self, on_change: Callable[[], None], delay_ms: int = 300) -> None:
        self._on_change, self._delay_ms = on_change, delay_ms
        self._monitor: Gio.FileMonitor | None = None
        self._timer = 0

    def watch(self, folder: str) -> None:
        """Follow `folder` instead of whatever was followed before."""
        self.stop()
        try:
            monitor = Gio.File.new_for_path(folder).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        except GLib.Error:
            return  # a folder that cannot be followed is still refreshed when the window comes back
        monitor.connect("changed", self._on_event)
        self._monitor = monitor

    def stop(self) -> None:
        if self._monitor is not None:
            self._monitor.cancel()
            self._monitor = None
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _on_event(self, monitor, file, other, event) -> None:
        if not self._timer:
            self._timer = GLib.timeout_add(self._delay_ms, self._fire)

    def _fire(self) -> bool:
        self._timer = 0
        self._on_change()
        return GLib.SOURCE_REMOVE
