import subprocess

import gi
import pytest

gi.require_version("Gio", "2.0")
from gi.repository import Gio


@pytest.fixture
def bus(monkeypatch, bus_options):
    # A plain dbus-daemon, not Gio.TestDBus: TestDBus forks a copy of the test process to watch the
    # bus, and once a GTK test has played media that copy outlives the run, spinning and holding its
    # output open. Its down() also waits ~30 s for the g_bus_get() singleton GTK keeps alive.
    daemon = subprocess.Popen(
        ["dbus-daemon", *bus_options, "--nofork", "--print-address=1"], stdout=subprocess.PIPE, text=True
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
