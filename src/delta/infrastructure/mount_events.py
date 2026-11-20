"""MountEvents on Gio.VolumeMonitor: says when a drive or folder gets mounted."""

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio


class GioMountEvents:
    def __init__(self, monitor: Gio.VolumeMonitor | None = None) -> None:
        self._monitor = monitor if monitor is not None else Gio.VolumeMonitor.get()

    def watch(self, callback: Callable[[], None]) -> None:
        self._monitor.connect("mount-added", lambda _monitor, _mount: callback())
