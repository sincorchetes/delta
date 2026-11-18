#!/usr/bin/env python3
"""Times the daemon's read-only questions about a path, in your real session.

    uv run python scripts/bench_dbus.py ~/Pictures

This is what the versions window waits for. Run it TWICE: the daemon keeps what `borg list` said in
memory (snapshots never change), so the second run shows what that saves. Nothing is written.
"""

import sys
import time
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

NAME, PATH, IFACE = "io.github.sincorchetes.Delta.Service1", "/io/github/sincorchetes/Delta/Service1", "io.github.sincorchetes.Delta.Service1"
TIMEOUT_MS = 600_000


def ask(bus, method, params=None):
    """(seconds, rows or None, error or None)"""
    started = time.monotonic()
    try:
        rows = bus.call_sync(NAME, PATH, IFACE, method, params, None, Gio.DBusCallFlags.NONE, TIMEOUT_MS, None).unpack()[0]
        return time.monotonic() - started, rows, None
    except GLib.Error as err:
        return time.monotonic() - started, None, err.message.split(": ", 1)[-1]


def report(label, took, rows, error):
    detail = f"{len(rows)} rows" if rows is not None else f"FAILED: {error}"
    print(f"  {label:<34} {took:7.2f} s   {detail}")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    path = str(Path(sys.argv[1]).expanduser().resolve())
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    print(f"path: {path}\n")

    took, snapshots, error = ask(bus, "ListSnapshots")
    report("ListSnapshots", took, snapshots, error)
    if not snapshots:
        return 1
    newest = max(snapshots, key=lambda row: row["time"])["id"]
    print(f"    ({len(snapshots)} snapshots; asking about the newest)\n")

    report("ListVersions (one borg call per snapshot)", *ask(bus, "ListVersions", GLib.Variant("(s)", (path,))))
    folder = GLib.Variant("(ss)", (newest, path))
    report("ListFolder", *ask(bus, "ListFolder", folder))
    report("ListChanged  (1st: borg + disk)", *ask(bus, "ListChanged", folder))
    report("ListChanged  (2nd: cached listing)", *ask(bus, "ListChanged", folder))
    report("ListDeleted", *ask(bus, "ListDeleted", folder))
    report("SearchFolder 'a'", *ask(bus, "SearchFolder", GLib.Variant("(sss)", (newest, path, "a"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
