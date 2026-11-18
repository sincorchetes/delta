"""Cheap guard for the widget code, which cannot be exercised without a display."""

import gi
import pytest

try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
except ValueError:
    pytest.skip("GTK 4 / libadwaita typelibs not available", allow_module_level=True)


def test_the_widget_modules_import_without_a_display():
    from delta.ui import (
        application,
        history_window,
        path_list,
        preferences_dialog,
        versions_window,
        window,
        wizard_destination,
        wizard_pages,
        wizard_window,
    )

    assert history_window.HistoryWindow is not None
    assert versions_window.VersionsWindow is not None
    assert path_list.PathListGroup is not None
    assert preferences_dialog.PreferencesDialog is not None
    assert application.APPLICATION_ID == "io.github.sincorchetes.Delta"
    assert window.StatusWindow is not None
    assert wizard_window.SetupWizard is not None
    assert wizard_destination.DestinationPage is not None
    assert wizard_pages.FoldersPage is not None
    assert wizard_pages.RecoveryPage is not None


def test_the_app_and_the_daemon_never_share_an_application_id():
    """Sharing it would hand the app's activation to the windowless daemon."""
    from delta.daemon.main import APPLICATION_ID as daemon_id
    from delta.ui.application import APPLICATION_ID as app_id

    assert app_id != daemon_id


def test_the_file_given_with_versions_is_decoded_from_glibs_bytes():
    from delta.ui.application import versions_path

    assert versions_path(b"/home/ana/Documents/a.odt\0") == "/home/ana/Documents/a.odt"
    as_unpacked_by_pygobject = list(b"/home/ana/Pictures/Profile.pdf\0")  # an `ay` is a list of ints
    assert versions_path(as_unpacked_by_pygobject) == "/home/ana/Pictures/Profile.pdf"
    assert versions_path([0]) is None and versions_path([]) is None
    assert versions_path("/home/ana/a.txt") == "/home/ana/a.txt"
    assert versions_path(None) is None and versions_path(b"") is None
