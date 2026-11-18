"""D-Bus client for the Delta daemon, used by the GTK app. Never blocks the main loop."""

import re
from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

BUS_NAME = "io.github.sincorchetes.Delta.Service1"
OBJECT_PATH = "/io/github/sincorchetes/Delta/Service1"
INTERFACE = "io.github.sincorchetes.Delta.Service1"
PROPERTIES = "org.freedesktop.DBus.Properties"
TIMEOUT_MS = 30_000

# (value, error): exactly one of them is not None.
Reply = Callable[[Any, "str | None"], None]
_REMOTE_PREFIX = re.compile(r"^GDBus\.Error:[^:]+:\s*")


def readable(error: GLib.Error) -> str:
    """The daemon's own message, without the 'GDBus.Error:<name>:' prefix."""
    return _REMOTE_PREFIX.sub("", error.message)


class DeltaClient:
    def __init__(self, connection: Gio.DBusConnection, bus_name: str = BUS_NAME) -> None:
        self._connection = connection
        self._bus_name = bus_name  # overridable so tests can target a unique name

    def read_state(self, reply: Reply) -> None:
        """Status, LastBackup and LastError as a dict; an error means the daemon is unreachable."""
        self._call(
            PROPERTIES, "GetAll", GLib.Variant("(s)", (INTERFACE,)), reply,
            lambda value: value.unpack()[0],
        )

    def list_snapshots(self, reply: Reply) -> None:
        """Rows with `id`, `name` and `time` (epoch seconds)."""
        self._call(INTERFACE, "ListSnapshots", None, reply, lambda value: value.unpack()[0])

    def list_versions(self, path: str, reply: Reply) -> None:
        """Distinct versions of one file across the backups: rows with `name`, `time`, `mtime`, `size`."""
        self._call(
            INTERFACE, "ListVersions", GLib.Variant("(s)", (path,)), reply,
            lambda value: value.unpack()[0],
        )

    def list_folder(self, snapshot: str, path: str, reply: Reply) -> None:
        """What a folder held in one snapshot, one level: rows with `name`, `is_dir`, `size`, `mtime`."""
        self._call(
            INTERFACE, "ListFolder", GLib.Variant("(ss)", (snapshot, path)), reply,
            lambda value: value.unpack()[0],
        )

    def search_folder(self, snapshot: str, path: str, query: str, reply: Reply) -> None:
        """Entries anywhere below a folder, in one snapshot, whose name has `query`: rows like
        `list_folder`, with `name` the path relative to the folder. At most 1000."""
        self._call(
            INTERFACE, "SearchFolder", GLib.Variant("(sss)", (snapshot, path, query)), reply,
            lambda value: value.unpack()[0],
        )

    def list_deleted(self, snapshot: str, folder: str, reply: Reply) -> None:
        """What a folder held in one snapshot that is gone from the disk today, folders counted as
        one item: rows with `name` (relative to the folder), `is_dir`, `size`, `mtime`."""
        self._call(
            INTERFACE, "ListDeleted", GLib.Variant("(ss)", (snapshot, folder)), reply,
            lambda value: value.unpack()[0],
        )

    def list_changed(self, snapshot: str, folder: str, reply: Reply) -> None:
        """Like `list_deleted`, plus every file that differs from today's, at any depth."""
        self._call(
            INTERFACE, "ListChanged", GLib.Variant("(ss)", (snapshot, folder)), reply,
            lambda value: value.unpack()[0],
        )

    def restore_deleted(self, snapshot: str, folder: str, reply: Reply) -> None:
        """Put all of that back under its own name; the finished job's message is how many items."""
        self._call(
            INTERFACE, "RestoreDeleted", GLib.Variant("(ss)", (snapshot, folder)), reply,
            lambda value: value.unpack()[0],
        )

    def restore_as_copy(self, snapshot: str, path: str, reply: Reply) -> None:
        """Put the old version beside the original; the finished job's message is the new path."""
        self._call(
            INTERFACE, "RestoreAsCopy", GLib.Variant("(ss)", (snapshot, path)), reply,
            lambda value: value.unpack()[0],
        )

    def restore_replace(self, snapshot: str, path: str, reply: Reply) -> None:
        """Put the old version in place; the current one is kept aside under a dated name."""
        self._call(
            INTERFACE, "RestoreReplace", GLib.Variant("(ss)", (snapshot, path)), reply,
            lambda value: value.unpack()[0],
        )

    def preview_version(self, snapshot: str, path: str, reply: Reply) -> None:
        """Unpack the old version read-only; the finished job's message is where it is."""
        self._call(
            INTERFACE, "PreviewVersion", GLib.Variant("(ss)", (snapshot, path)), reply,
            lambda value: value.unpack()[0],
        )

    def mount_snapshot(self, snapshot: str, reply: Reply) -> None:
        """Open one backup as a read-only folder; the finished job's message is where it is. It can
        take a few seconds: a backup that is running has to stop first."""
        self._call(
            INTERFACE, "MountSnapshot", GLib.Variant("(s)", (snapshot,)), reply,
            lambda value: value.unpack()[0],
        )

    def unmount_snapshot(self, reply: Reply) -> None:
        """Close the open backup. The job is None when none was open."""
        self._call(INTERFACE, "UnmountSnapshot", None, reply, lambda value: value.unpack()[0] or None)

    def clear_previews(self) -> None:
        """Ask the daemon to forget every preview, and wait: the app may exit right after."""
        try:
            self._connection.call_sync(
                self._bus_name, OBJECT_PATH, INTERFACE, "ClearPreviews", None, None,
                Gio.DBusCallFlags.NO_AUTO_START, 2000, None,
            )
        except GLib.Error:
            pass  # no daemon, nothing to clear; it also clears its own previews at start and stop

    def create_backup(self, reply: Reply) -> None:
        self._call(INTERFACE, "CreateBackup", None, reply, lambda value: value.unpack()[0])

    def create_repository(self, location: str, passphrase: str, reply: Reply) -> None:
        """An empty passphrase makes the daemon generate one and keep it in the keyring."""
        self._call(
            INTERFACE, "CreateRepository", GLib.Variant("(ss)", (location, passphrase)), reply,
            lambda value: value.unpack()[0],
        )

    def unlock_repository(self, reply: Reply) -> None:
        """Remove a stale lock. Only ever on an explicit, confirmed request from the user."""
        self._call(INTERFACE, "UnlockRepository", None, reply, lambda value: value.unpack()[0])

    def use_repository(self, location: str, passphrase: str, reply: Reply) -> None:
        """Adopt a repository that already exists; the daemon checks the passphrase opens it."""
        self._call(
            INTERFACE, "UseRepository", GLib.Variant("(ss)", (location, passphrase)), reply,
            lambda value: value.unpack()[0],
        )

    def on_backup_finished(self, handler: Callable[[str, bool, str], None]) -> int:
        return self._subscribe("BackupFinished", lambda args: handler(*args))

    def on_progress(self, handler: Callable[[str, float, str], None]) -> int:
        return self._subscribe("Progress", lambda args: handler(*args))

    def on_snapshot_closed(self, handler: Callable[[str], None]) -> int:
        """The daemon closed the open backup (reason: requested, owner-gone, sleep-or-lock, ...)."""
        return self._subscribe("SnapshotClosed", lambda args: handler(*args))

    def unsubscribe(self, subscription: int) -> None:
        self._connection.signal_unsubscribe(subscription)

    def _subscribe(self, signal: str, deliver: Callable[[tuple], None]) -> int:
        def on_signal(connection, sender, path, interface, name, parameters, *extra) -> None:
            deliver(parameters.unpack())

        return self._connection.signal_subscribe(
            self._bus_name, INTERFACE, signal, OBJECT_PATH, None,
            Gio.DBusSignalFlags.NONE, on_signal,
        )

    def _call(self, interface: str, method: str, parameters, reply: Reply, convert) -> None:
        def done(connection, result) -> None:
            try:
                value = convert(connection.call_finish(result))
            except GLib.Error as err:
                reply(None, readable(err))
                return
            reply(value, None)

        # No NO_AUTO_START flag: the first call activates the daemon.
        self._connection.call(
            self._bus_name, OBJECT_PATH, interface, method, parameters, None,
            Gio.DBusCallFlags.NONE, TIMEOUT_MS, None, done,
        )
