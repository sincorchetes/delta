"""The GTK application (io.github.sincorchetes.Delta). The daemon is a separate process and id."""

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from delta import i18n
from delta.i18n import _
from delta.infrastructure.runtime import in_flatpak
from delta.infrastructure.settings import open_settings
from delta.ui.client import DeltaClient
from delta.ui.help import has_viewer, help_uri, manual_installed
from delta.ui.versions_window import VersionsWindow
from delta.ui.window import StatusWindow

APPLICATION_ID = "io.github.sincorchetes.Delta"


def versions_path(raw: object) -> str | None:
    """The file named by `--versions`.

    GLib stores a filename option as a NUL-terminated byte array (`ay`), which PyGObject unpacks
    as a list of ints; bytes and plain strings are accepted too.
    """
    if isinstance(raw, (list, tuple)) and all(isinstance(item, int) for item in raw):
        raw = bytes(raw)
    if isinstance(raw, bytes):
        raw = os.fsdecode(raw.rstrip(b"\0"))
    return raw if isinstance(raw, str) and raw else None


class DeltaApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APPLICATION_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        )
        self.add_main_option(
            "versions", 0, GLib.OptionFlags.NONE, GLib.OptionArg.FILENAME,
            _("Show the previous versions of a file"), "FILE",
        )
        self._status: StatusWindow | None = None
        self._client: DeltaClient | None = None
        help_action = Gio.SimpleAction.new("help", None)
        help_action.connect("activate", lambda action, parameter: self.show_help())
        self.add_action(help_action)
        self.set_accels_for_action("app.help", ["F1"])

    def show_help(self) -> None:
        """The manual in Yelp when this computer has it and a viewer for it; otherwise the same one on the web."""
        uri = help_uri(in_flatpak(), manual_installed(), has_viewer())
        Gtk.UriLauncher.new(uri).launch(self.get_active_window(), None, None)

    def do_command_line(self, command_line) -> int:
        raw = command_line.get_options_dict().end().unpack().get("versions")
        path = versions_path(raw)
        if path is None:
            self.activate()
            return 0
        target = command_line.create_file_for_arg(path).get_path()
        if target is None:
            return 1
        VersionsWindow(self, self._client_for_session(), target).present()
        return 0

    def do_activate(self) -> None:
        if self._status is None:
            self._status = StatusWindow(self, self._client_for_session(), open_settings())
            self._status.connect("destroy", lambda window: setattr(self, "_status", None))
        self._status.present()

    def _client_for_session(self) -> DeltaClient:
        if self._client is None:
            self._client = DeltaClient(Gio.bus_get_sync(Gio.BusType.SESSION, None))
        return self._client


def main() -> int:
    i18n.setup()
    return DeltaApplication().run(sys.argv)
