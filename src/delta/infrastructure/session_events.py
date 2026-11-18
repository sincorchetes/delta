"""SessionEvents on logind (going to sleep) and GNOME's screen lock."""

import logging
import os
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from delta.i18n import _

log = logging.getLogger(__name__)

LOGIND = ("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager")
SOURCES = (
    (Gio.BusType.SYSTEM, LOGIND[0], LOGIND[2], "PrepareForSleep"),
    (Gio.BusType.SESSION, "org.gnome.ScreenSaver", "org.gnome.ScreenSaver", "ActiveChanged"),
)


class LogindSessionEvents:
    """Both signals carry a boolean that is true when the sleep or the lock begins."""

    def __init__(self) -> None:
        self._lock_fd: int | None = None

    def watch(self, callback: Callable[[], None]) -> None:
        for bus_type, name, interface, signal in SOURCES:
            try:
                connection = Gio.bus_get_sync(bus_type, None)
            except GLib.Error as err:
                log.warning("cannot watch %s: %s", signal, err.message)
                continue
            connection.signal_subscribe(
                name, interface, signal, None, None, Gio.DBusSignalFlags.NONE, self._on_signal, callback
            )

    @staticmethod
    def _on_signal(_connection, _sender, _path, _interface, _signal, parameters, callback) -> None:
        if parameters.unpack()[0]:
            callback()

    def hold(self) -> None:
        """Ask logind to wait (a few seconds at most) before sleeping, until `release`: time to
        close the open snapshot first. Without it, the computer could sleep with the folder mounted."""
        if self._lock_fd is not None:
            return
        try:
            connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            reply, fds = connection.call_with_unix_fd_list_sync(
                LOGIND[0], LOGIND[1], LOGIND[2], "Inhibit",
                GLib.Variant("(ssss)", ("sleep", "Delta", _("Closing the open backup"), "delay")),
                GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1, None, None,
            )
            self._lock_fd = fds.get(reply.unpack()[0])
        except GLib.Error as err:
            log.warning("cannot delay sleeping: %s", err.message)

    def release(self) -> None:
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
