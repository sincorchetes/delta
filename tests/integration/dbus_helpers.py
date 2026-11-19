"""What the D-Bus tests share: the names of the service and two ways of calling it.

Not in conftest.py: a test that imports from `conftest` gets whichever conftest of the three (tests/, tests/gtk/,
tests/integration/) pytest loaded last, which depends on its version.
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

IFACE, PATH = "io.github.sincorchetes.Delta.Service1", "/io/github/sincorchetes/Delta/Service1"


def call_rows(bus, method, parameters, timeout_ms=15000):
    """Call a method that answers with `aa{sv}` rows. Returns {"rows": [...]} or {"error": text}."""
    loop = GLib.MainLoop()
    outcome = {}

    def done(connection, result):
        try:
            outcome["rows"] = connection.call_finish(result).unpack()[0]
        except GLib.Error as err:
            outcome["error"] = err.message
        loop.quit()

    bus.call(
        bus.get_unique_name(), PATH, IFACE, method, parameters, None,
        Gio.DBusCallFlags.NONE, 5000, None, done,
    )
    GLib.timeout_add(timeout_ms, loop.quit)
    loop.run()
    return outcome


def call_and_wait_finished(bus, method, parameters=None, timeout_ms=15000):
    """Call `method` asynchronously and wait for BackupFinished.

    Returns (job_id, finished_params, error_message).
    """
    loop = GLib.MainLoop()
    outcome = {}

    def on_finished(*args):
        outcome["finished"] = args[-1].unpack()
        loop.quit()

    def on_reply(connection, result):
        try:
            outcome["job_id"] = connection.call_finish(result).unpack()[0]
        except GLib.Error as err:
            outcome["error"] = err.message
            loop.quit()

    bus.signal_subscribe(None, IFACE, "BackupFinished", PATH, None, Gio.DBusSignalFlags.NONE, on_finished)
    bus.call(
        bus.get_unique_name(), PATH, IFACE, method, parameters, None,
        Gio.DBusCallFlags.NONE, 5000, None, on_reply,
    )
    GLib.timeout_add(timeout_ms, loop.quit)
    loop.run()
    return outcome.get("job_id"), outcome.get("finished"), outcome.get("error")
