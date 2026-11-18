"""Domain objects as the `a{sv}` rows the D-Bus API returns."""

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib


def snapshot_to_variant(snapshot) -> dict:
    return {
        "id": GLib.Variant("s", snapshot.id),
        "name": GLib.Variant("s", snapshot.name),
        "time": GLib.Variant("x", int(snapshot.created.timestamp())),
    }


def folder_entry_to_variant(entry) -> dict:
    return {
        "name": GLib.Variant("s", entry.name),
        "is_dir": GLib.Variant("b", entry.is_dir),
        "size": GLib.Variant("x", entry.size),
        "mtime": GLib.Variant("x", int(entry.mtime.timestamp())),
    }


def version_to_variant(version) -> dict:
    row = snapshot_to_variant(version.snapshot)
    row["size"] = GLib.Variant("x", version.entry.size)
    row["mtime"] = GLib.Variant("x", int(version.entry.mtime.timestamp()))
    row["is_dir"] = GLib.Variant("b", version.entry.is_dir)
    return row
