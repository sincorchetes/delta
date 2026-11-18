"""The versions of the opened item, newest first, as a list to pick one from."""

from collections.abc import Callable

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from delta.ui.versions import VersionRow, step_index


class Timeline(Gtk.ScrolledWindow):
    def __init__(self, on_select: Callable[[VersionRow | None], None], on_open: Callable[[], None]) -> None:
        """`on_select(version)`: a different version was chosen. `on_open()`: double click or Enter."""
        super().__init__(
            hscrollbar_policy=Gtk.PolicyType.NEVER, width_request=290,
            margin_start=12, margin_end=12, margin_top=12, margin_bottom=12,
        )
        self._versions: list[VersionRow] = []
        self._on_select = on_select
        self._handled: int | None = None  # the row whose version is being shown
        # A single click only selects (and shows) a version; opening it outside is double click or Enter.
        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, activate_on_single_click=False)
        self._list.add_css_class("boxed-list")
        self._list.connect("row-selected", self._on_row_selected)
        self._list.connect("row-activated", lambda listbox, row: on_open())
        self.set_child(self._list)

    @property
    def selected(self) -> VersionRow | None:
        row = self._list.get_selected_row()
        return self._versions[row.get_index()] if row is not None else None

    def fill(self, versions: list[VersionRow]) -> None:
        """Show these (newest first) and choose the first."""
        self._versions = versions
        for version in versions:
            self._list.append(
                Adw.ActionRow(
                    title=GLib.markup_escape_text(version.modified),
                    subtitle=GLib.markup_escape_text(version.backed_up),
                    activatable=True,
                )
            )
        self._list.select_row(self._list.get_row_at_index(0))

    def step(self, delta: int) -> None:
        """Choose the version `delta` places further down (older) or up (newer), if there is one."""
        row = self._list.get_selected_row()
        index = step_index(None if row is None else row.get_index(), delta, len(self._versions))
        target = None if index is None else self._list.get_row_at_index(index)
        if target is not None:
            self._list.select_row(target)
            target.grab_focus()  # which also scrolls it into view

    def _on_row_selected(self, listbox, row) -> None:
        # GTK also emits this when focus merely moves into the list (for instance when the folder
        # browser is hidden to show a file), with the same row: that is not a new choice, and
        # treating it as one threw the user back to the top of the folder.
        index = None if row is None else row.get_index()
        if index == self._handled:
            return
        self._handled = index
        self._on_select(self.selected)
