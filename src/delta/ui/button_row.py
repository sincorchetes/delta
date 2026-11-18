"""A row of buttons that breaks into lines when the window is narrow, instead of making the window wider."""

from collections.abc import Iterable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GObject, Gtk

GAP = 12


def button_row(buttons: Iterable[Gtk.Button]) -> Gtk.FlowBox:
    """Buttons side by side while they fit, in several lines when they do not (long translations)."""
    buttons = list(buttons)
    row = Gtk.FlowBox(
        selection_mode=Gtk.SelectionMode.NONE,
        homogeneous=False,
        halign=Gtk.Align.CENTER,
        max_children_per_line=len(buttons),
        column_spacing=GAP,
        row_spacing=GAP,
        margin_start=GAP,
        margin_end=GAP,
        margin_top=GAP,
        margin_bottom=GAP,
    )
    for button in buttons:
        slot = Gtk.FlowBoxChild(child=button, focusable=False)  # the keyboard stops at the button, not at its slot
        button.bind_property("visible", slot, "visible", GObject.BindingFlags.SYNC_CREATE)
        row.append(slot)
    return row
