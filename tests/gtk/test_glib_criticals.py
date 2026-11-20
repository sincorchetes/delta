"""A GLib CRITICAL fails the test it happens in (tests/gtk/conftest.py)."""

from gi.repository import Adw, Gio, Gtk


def test_a_critical_of_gtk_is_recorded_with_its_domain_and_message(no_glib_criticals):
    # The one that #36 found 51 times: a window given to an application that has not started up. Not registered, so
    # its id is not exported on the bus.
    application = Adw.Application(application_id="io.github.sincorchetes.CriticalTest", flags=Gio.ApplicationFlags.NON_UNIQUE)

    window = Gtk.ApplicationWindow(application=application)

    assert any(found.startswith("Gtk: ") and "startup" in found for found in no_glib_criticals), no_glib_criticals
    no_glib_criticals.clear()  # it was provoked on purpose: the test must not fail for it
    window.destroy()
