"""The Background portal: lets a Flatpak keep running and start itself when the user logs in.

Without it the daemon of a Flatpak only lives while the window is open, so a schedule would only work then.
The portal asks the user once, in the desktop's own dialog; the answer is kept by the system.
"""

import logging
import uuid
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from delta.i18n import _

log = logging.getLogger(__name__)

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
BACKGROUND = "org.freedesktop.portal.Background"
REQUEST = "org.freedesktop.portal.Request"
GRANTED = 0  # the portal's answer for "the user said yes"
DAEMON = ["delta-daemon"]  # a command of the sandbox: the portal starts it with `flatpak run --command=`


class BackgroundPortal:
    def __init__(self, connection: Gio.DBusConnection, token: Callable[[], str] = lambda: uuid.uuid4().hex) -> None:
        self._connection = connection
        self._token = token

    def request(self, on_answer: Callable[[bool], None]) -> None:
        """Ask to run in the background and start at login; `on_answer(True)` only if both were granted."""
        token = self._token()
        sender = self._connection.get_unique_name().lstrip(":").replace(".", "_")
        # The reply of a request comes as a signal on a path that is known beforehand: listen before asking.
        subscription = self._connection.signal_subscribe(
            PORTAL, REQUEST, "Response", f"{PORTAL_PATH}/request/{sender}/{token}", None, Gio.DBusSignalFlags.NONE,
            lambda *args: self._answered(subscription, args[-1], on_answer),
        )
        options = {
            "handle_token": GLib.Variant("s", token),
            "reason": GLib.Variant("s", _("Delta makes your scheduled backups when you are not using it")),
            "autostart": GLib.Variant("b", True),
            "commandline": GLib.Variant("as", DAEMON),
            "dbus-activatable": GLib.Variant("b", False),
        }
        self._connection.call(
            PORTAL, PORTAL_PATH, BACKGROUND, "RequestBackground", GLib.Variant("(sa{sv})", ("", options)),
            None, Gio.DBusCallFlags.NONE, -1, None,
            lambda connection, result: self._asked(connection, result, subscription, on_answer),
        )

    def _asked(self, connection, result, subscription: int, on_answer: Callable[[bool], None]) -> None:
        try:
            connection.call_finish(result)
        except GLib.Error as err:
            log.warning("cannot ask the background portal: %s", err.message)
            self._connection.signal_unsubscribe(subscription)
            on_answer(False)

    def _answered(self, subscription: int, parameters, on_answer: Callable[[bool], None]) -> None:
        self._connection.signal_unsubscribe(subscription)
        response, results = parameters.unpack()
        on_answer(response == GRANTED and bool(results.get("background")) and bool(results.get("autostart")))
