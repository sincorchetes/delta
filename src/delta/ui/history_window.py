"""The backup history: every snapshot in the repository, as a table."""

from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, GObject, Gtk, Pango

from delta.i18n import _
from delta.ui.a11y import loading_spinner
from delta.ui.client import DeltaClient
from delta.ui.history import HistoryRow, build_history, describe_count
from delta.ui.status import summarise


class Row(GObject.Object):
    name = GObject.Property(type=str)
    when = GObject.Property(type=str)
    ago = GObject.Property(type=str)

    @classmethod
    def of(cls, row: HistoryRow) -> "Row":
        return cls(name=row.name, when=row.when, ago=row.ago)


def _column(title: str, attribute: str, expand: bool = False) -> Gtk.ColumnViewColumn:
    def setup(factory, item) -> None:
        item.set_child(
            Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, margin_top=6, margin_bottom=6)
        )

    def bind(factory, item) -> None:
        item.get_child().set_text(getattr(item.get_item(), attribute))

    factory = Gtk.SignalListItemFactory()
    factory.connect("setup", setup)
    factory.connect("bind", bind)
    return Gtk.ColumnViewColumn(title=title, factory=factory, expand=expand, resizable=True)


class HistoryWindow(Adw.Window):
    def __init__(self, parent, client: DeltaClient) -> None:
        super().__init__(
            transient_for=parent, title=_("Backup history"), default_width=520, default_height=480
        )
        self._store = Gio.ListStore.new(Row)
        table = Gtk.ColumnView(model=Gtk.NoSelection(model=self._store), show_column_separators=True)
        table.append_column(_column(_("Date"), "when"))
        table.append_column(_column(_("Age"), "ago"))
        table.append_column(_column(_("Name"), "name", expand=True))

        self._count = Gtk.Label(xalign=0, margin_start=12, margin_top=6, margin_bottom=6)
        listing = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        listing.append(self._count)
        listing.append(Gtk.ScrolledWindow(child=table, vexpand=True))

        self._empty = Adw.StatusPage(icon_name="document-open-recent-symbolic")
        self._stack = Gtk.Stack()
        self._stack.add_named(loading_spinner(halign=Gtk.Align.CENTER), "loading")
        self._stack.add_named(listing, "list")
        self._stack.add_named(self._empty, "empty")

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(self._stack)
        self.set_content(toolbar)

        self._stack.set_visible_child_name("loading")
        client.list_snapshots(self._on_rows)

    def _on_rows(self, rows, error) -> None:
        if error:
            self._show_empty(_("Could not read the backups"), summarise(error))
            return
        history = build_history(rows, datetime.now())
        if not history:
            self._show_empty(_("No backups yet"), "")
            return
        self._store.splice(0, 0, [Row.of(item) for item in history])
        self._count.set_text(describe_count(len(history)))
        self._stack.set_visible_child_name("list")

    def _show_empty(self, title: str, detail: str) -> None:
        self._empty.set_title(title)
        self._empty.set_description(GLib.markup_escape_text(detail))
        self._stack.set_visible_child_name("empty")
