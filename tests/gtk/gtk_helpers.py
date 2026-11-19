"""Finding widgets in a tree.

Not in conftest.py: a test that imports from `conftest` gets whichever conftest of the three (tests/, tests/gtk/,
tests/integration/) pytest loaded last, which depends on its version.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


def descendants(widget):
    """Every widget below `widget`, depth first."""
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from descendants(child)
        child = child.get_next_sibling()


def of_type(widget, kind):
    return [found for found in descendants(widget) if isinstance(found, kind)]


def labels(widget):
    return [label.get_text() for label in of_type(widget, Gtk.Label)]
