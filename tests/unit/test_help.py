"""Where F1 goes, from what this computer has."""

import pytest
from gi.repository import Gio

from delta.ui import help as helpers
from delta.ui.help import LOCAL_URI, WEB_URI, has_viewer, help_uri, manual_installed


@pytest.mark.parametrize(
    ("sandboxed", "manual", "viewer", "expected"),
    [
        (False, True, True, LOCAL_URI),  # the one case with everything in place
        (False, True, False, WEB_URI),  # no Yelp: an application chooser with nothing in it would open
        (False, False, True, WEB_URI),  # the install does not link the manual: Yelp would not find it
        (False, False, False, WEB_URI),
        (True, True, True, WEB_URI),  # a Flatpak: its pages are inside the sandbox, out of Yelp's reach
        (True, False, False, WEB_URI),
    ],
)
def test_only_a_native_install_with_the_manual_and_a_viewer_opens_it_locally(sandboxed, manual, viewer, expected):
    assert help_uri(sandboxed, manual, viewer) == expected


def test_the_addresses_are_the_manual_of_the_application_and_its_website():
    assert LOCAL_URI == "help:delta" and WEB_URI == "https://delta.sincorchetes.tech"


def test_the_manual_is_found_in_any_of_the_data_directories(tmp_path):
    page = tmp_path / "second" / "help" / "C" / "delta"
    page.mkdir(parents=True)
    (page / "index.page").write_text("<page/>")

    assert manual_installed([str(tmp_path / "first"), str(tmp_path / "second")]) is True
    assert manual_installed([str(tmp_path / "first")]) is False


def test_by_default_the_user_and_system_data_directories_are_searched(monkeypatch):
    searched = []
    monkeypatch.setattr(helpers.os.path, "exists", lambda path: searched.append(path) or False)

    assert manual_installed() is False
    assert any(path.endswith("help/C/delta/index.page") for path in searched) and len(searched) >= 2


def test_a_viewer_is_whatever_is_registered_for_help_addresses(monkeypatch):
    monkeypatch.setattr(Gio.AppInfo, "get_default_for_uri_scheme", staticmethod(lambda scheme: object()))
    assert has_viewer() is True

    monkeypatch.setattr(Gio.AppInfo, "get_default_for_uri_scheme", staticmethod(lambda scheme: None))
    assert has_viewer() is False
