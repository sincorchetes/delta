"""Finding widgets in a tree, and an application to give windows to.

Not in conftest.py: a test that imports from `conftest` gets whichever conftest of the three (tests/, tests/gtk/,
tests/integration/) pytest loaded last, which depends on its version.
"""

import itertools

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

_numbers = itertools.count()


def started_application(name):
    """An application that has gone through `startup`, as GTK wants before it is given a window.

    Each one has an id of its own: GApplication exports its id on the bus, the same id cannot be exported twice by one
    process, and an application cannot be taken off the bus once it is registered.
    """
    application = Adw.Application(
        application_id=f"io.github.sincorchetes.{name}{next(_numbers)}", flags=Gio.ApplicationFlags.NON_UNIQUE
    )
    application.register(None)
    return application


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
