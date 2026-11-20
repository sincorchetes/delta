"""A GLib CRITICAL fails the test it happens in (tests/gtk/conftest.py)."""

from gi.repository import Adw, Gio, Gtk


def test_a_critical_of_gtk_is_seen_with_its_domain_and_message(capfd):
    # The one that #36 found 51 times: a window given to an application that has not started up. Not registered, so
    # its id is not exported on the bus.
    application = Adw.Application(application_id="io.github.sincorchetes.CriticalTest", flags=Gio.ApplicationFlags.NON_UNIQUE)

    window = Gtk.ApplicationWindow(application=application)

    printed = capfd.readouterr().err  # provoked on purpose: reading it keeps the test from failing for it
    assert "Gtk-CRITICAL **" in printed and "GApplication::startup" in printed, printed
    window.destroy()
