"""Names for what a screen reader would otherwise read out as just «button», «check box» or «image»."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from delta.i18n import _


def named(widget, text: str):
    """Give `widget` the accessible name `text` (a tooltip alone is not a reliable name)."""
    widget.update_property([Gtk.AccessibleProperty.LABEL], [text])
    return widget


def tipped(widget, text: str):
    """An icon-only control: `text` is both its tooltip for those who see it and its name for those who hear it."""
    widget.set_tooltip_text(text)
    return named(widget, text)


def decorative_icon(icon_name: str) -> Gtk.Image:
    """An icon that repeats what the text beside it says: invisible to a screen reader."""
    return Gtk.Image(icon_name=icon_name, accessible_role=Gtk.AccessibleRole.PRESENTATION)


def loading_spinner(**properties) -> Gtk.Spinner:
    return named(Gtk.Spinner(spinning=True, **properties), _("Loading…"))
