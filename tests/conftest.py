"""Shared by the whole suite: it never talks to the session bus, or the keyring, of whoever runs it.

GLib keeps a single connection to the session bus for the whole process (the one `g_bus_get()` hands out) and libsecret
uses it. Whichever test needs a bus first fixes it: on a desktop that is the machine's own session, on a CI runner too, so
the tests that start their own keyring end up talking to a bus that does not have it (or, worse, to the real keyring of
the person running the tests). One private bus is started before the first test and pinned as that connection.
"""

import os
import shutil
import subprocess

import gi
import pytest

gi.require_version("Gio", "2.0")
from gi.repository import Gio


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
    """The options that start a session bus on this machine, for the tests that start their own."""
    return session_bus_options()


@pytest.fixture(scope="session", autouse=True)
def private_session_bus(bus_options):
    """The bus of the whole run. Yields its address, or None where there is no dbus-daemon to start one."""
    program = shutil.which("dbus-daemon")
    if program is None:
        yield None
        return
    daemon = subprocess.Popen([program, *bus_options, "--nofork", "--print-address=1"], stdout=subprocess.PIPE, text=True)
    assert daemon.stdout is not None
    address = daemon.stdout.readline().strip()
    if not address:
        daemon.kill()
        daemon.wait(timeout=5)
        daemon.stdout.close()
        yield None
        return
    environment = pytest.MonkeyPatch()
    environment.setenv("DBUS_SESSION_BUS_ADDRESS", address)
    Gio.bus_get_sync(Gio.BusType.SESSION, None)  # the connection that everything in this process shares
    yield address
    environment.undo()
    daemon.terminate()
    daemon.wait(timeout=5)
    daemon.stdout.close()
