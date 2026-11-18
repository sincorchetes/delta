"""LibsecretStore against a real gnome-keyring-daemon on an isolated bus.

The bus is the private one of the whole run (tests/conftest.py) and the daemon is module-scoped: libsecret uses the
g_bus_get() singleton, which Gio caches per process, so the session bus must outlive every test here and be fixed
before the first test that needs one.
"""

import os
import shutil
import subprocess
import time

import gi
import pytest

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

try:
    gi.require_version("Secret", "1")
except ValueError:
    pytest.skip("libsecret typelib not available", allow_module_level=True)

if shutil.which("gnome-keyring-daemon") is None:
    pytest.skip("gnome-keyring-daemon not installed", allow_module_level=True)

from gi.repository import Secret

from delta.infrastructure.libsecret_store import LibsecretStore

SECRETS_NAME = "org.freedesktop.secrets"


def _name_has_owner(connection) -> bool:
    reply = connection.call_sync(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "NameHasOwner",
        GLib.Variant("(s)", (SECRETS_NAME,)),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    return reply.unpack()[0]


@pytest.fixture(scope="module")
def store(tmp_path_factory, private_session_bus):
    # The keyring goes on the private bus of the whole run (tests/conftest.py): libsecret uses the connection
    # that g_bus_get() fixed for the process, and that is this bus, not the one of whoever runs the tests.
    if private_session_bus is None:
        pytest.skip("dbus-daemon not installed")
    address = private_session_bus
    root = tmp_path_factory.mktemp("keyring")
    runtime = root / "run"
    runtime.mkdir(mode=0o700)
    env = {
        **os.environ,
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_RUNTIME_DIR": str(runtime),
    }
    daemon = subprocess.Popen(
        ["gnome-keyring-daemon", "--foreground", "--components=secrets", "--unlock"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    assert daemon.stdin is not None
    daemon.stdin.write(b"test\n")
    daemon.stdin.close()
    connection = Gio.DBusConnection.new_for_address_sync(
        address,
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None,
        None,
    )
    deadline = time.monotonic() + 10
    while not _name_has_owner(connection):
        if time.monotonic() > deadline:
            daemon.kill()
            pytest.fail("gnome-keyring-daemon did not own org.freedesktop.secrets")
        time.sleep(0.1)
    yield LibsecretStore()
    Secret.Service.disconnect()  # drop libsecret's cached proxy before the bus goes away
    daemon.terminate()
    daemon.wait(timeout=5)
    connection.close_sync(None)


def test_missing_secret_is_none(store):
    assert store.get("/backups/none") is None


def test_set_then_get_round_trip(store):
    store.set("/srv/backups/roundtrip", "s3cret passphrase")
    assert store.get("/srv/backups/roundtrip") == "s3cret passphrase"


def test_set_overwrites_and_keys_are_independent(store):
    store.set("/overwrite/a", "one")
    store.set("/overwrite/b", "two")
    store.set("/overwrite/a", "three")
    assert (store.get("/overwrite/a"), store.get("/overwrite/b")) == ("three", "two")


def test_delete_removes_only_that_key(store):
    store.set("/delete/a", "one")
    store.set("/delete/b", "two")
    store.delete("/delete/a")
    assert (store.get("/delete/a"), store.get("/delete/b")) == (None, "two")
