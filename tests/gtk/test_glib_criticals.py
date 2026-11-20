"""A GLib CRITICAL fails the test it happens in (tests/gtk/conftest.py); anything milder does not."""

from gi.repository import GLib


def test_a_critical_is_recorded_with_its_domain_and_message(no_glib_criticals):
    GLib.log("Gtk", GLib.LogLevelFlags.LEVEL_CRITICAL, "something that should not happen")

    assert no_glib_criticals == ["Gtk: something that should not happen"]
    no_glib_criticals.clear()  # it was provoked on purpose: the test must not fail for it


def test_a_message_that_is_not_a_critical_is_not_recorded(no_glib_criticals):
    GLib.log("Gtk", GLib.LogLevelFlags.LEVEL_MESSAGE, "just so you know")
    GLib.log("Gtk", GLib.LogLevelFlags.LEVEL_WARNING, "a warning is not a critical")

    assert no_glib_criticals == []
