"""Keyboard shortcuts of the versions window."""

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

# What each key does; the window says how. Chosen to match Files and common GTK habits.
TRIGGERS = {
    "search": "<Control>f",  # go to the search box
    "back": "<Alt>Left",  # up one folder, or back from a file to the list (like Files)
    "older": "<Control>Down",  # the next older version
    "newer": "<Control>Up",  # the next newer version
    "escape": "Escape",  # clear the search, or leave selection mode
}


def install(widget: Gtk.Widget, actions: dict[str, Callable[[], bool | None]]) -> None:
    """Bind `actions` (keyed like `TRIGGERS`) on `widget`. An action that returns False has not
    used the key, so it carries on to whatever else wants it; anything else counts as used.

    Capture phase: the combinations are caught before a focused entry or list reads them as text.
    """
    controller = Gtk.ShortcutController(propagation_phase=Gtk.PropagationPhase.CAPTURE)
    for name, action in actions.items():
        trigger = Gtk.ShortcutTrigger.parse_string(TRIGGERS[name])
        controller.add_shortcut(
            Gtk.Shortcut.new(trigger, Gtk.CallbackAction.new(lambda w, args, act=action: act() is not False))
        )
    widget.add_controller(controller)
