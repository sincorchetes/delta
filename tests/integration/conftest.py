import os
import shutil
import subprocess

import gi
import pytest

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

IFACE, PATH = "io.github.sincorchetes.Delta.Service1", "/io/github/sincorchetes/Delta/Service1"


def session_bus_options() -> list[str]:
    """How to start a session bus: `--session` asks for /etc/dbus-1/session.conf, which not every system has.

    The dbus of Nix, for one, keeps its configuration in its own share/. The file next to the program is used when it is there.
    """
    program = shutil.which("dbus-daemon")
    if program is None:
        return ["--session"]
    config = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(program))), "share", "dbus-1", "session.conf")
    return ["--config-file", config] if os.path.exists(config) else ["--session"]


@pytest.fixture(scope="session")
def bus_options():
    """For the tests that start their own bus (the keyring ones): the options that `bus` uses."""
    return session_bus_options()


@pytest.fixture
def bus(monkeypatch):
    # A plain dbus-daemon, not Gio.TestDBus: TestDBus forks a copy of the test process to watch the
    # bus, and once a GTK test has played media that copy outlives the run, spinning and holding its
    # output open. Its down() also waits ~30 s for the g_bus_get() singleton GTK keeps alive.
    daemon = subprocess.Popen(
        ["dbus-daemon", *session_bus_options(), "--nofork", "--print-address=1"], stdout=subprocess.PIPE, text=True
    )
    try:
        address = daemon.stdout.readline().strip()
        assert address, "dbus-daemon did not print its address"
        monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", address)
        connection = Gio.DBusConnection.new_for_address_sync(
            address,
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None,
            None,
        )
        yield connection
        connection.close_sync(None)
    finally:
        daemon.terminate()
        daemon.wait(timeout=5)
        daemon.stdout.close()


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
