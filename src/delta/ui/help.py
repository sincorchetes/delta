"""Where F1 goes: the manual on this computer when it can be read, the same manual on the web when not."""

import os
from collections.abc import Iterable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

LOCAL_URI = "help:delta"
WEB_URI = "https://delta.sincorchetes.tech"
MANUAL_PAGE = os.path.join("help", "C", "delta", "index.page")


def manual_installed(data_dirs: Iterable[str] | None = None) -> bool:
    """The Mallard pages are somewhere Yelp looks (an install that does not link `share/help` has none)."""
    if data_dirs is None:
        data_dirs = [GLib.get_user_data_dir(), *GLib.get_system_data_dirs()]
    return any(os.path.exists(os.path.join(base, MANUAL_PAGE)) for base in data_dirs)


def has_viewer() -> bool:
    """Something is registered for `help:` addresses (Yelp, in GNOME)."""
    return Gio.AppInfo.get_default_for_uri_scheme("help") is not None


def help_uri(sandboxed: bool, manual: bool, viewer: bool) -> str:
    """A Flatpak's pages are inside its sandbox, where the Yelp of the computer cannot read them."""
    return LOCAL_URI if manual and viewer and not sandboxed else WEB_URI
