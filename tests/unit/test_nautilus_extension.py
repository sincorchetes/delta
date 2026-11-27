"""The extension runs inside Nautilus, so it is loaded here against a stand-in for Nautilus: its menu."""

import pytest
from nautilus_extension_support import FakeSchemaSource, FileInfo
from nautilus_extension_support import extension, provider  # noqa: F401  (fixtures)


@pytest.mark.parametrize(
    ("location", "shown"),
    [
        ("/run/media/ana/Disk/delta-backups", True),
        ("", False),
        ("   ", False),
        (None, True),  # Delta's settings are not installed here: cannot tell, so do not hide
    ],
)
def test_the_menu_is_hidden_only_when_delta_is_known_to_have_no_repository(extension, location, shown):
    assert extension.has_backups(location) is shown


@pytest.mark.parametrize("location", ["", "   "])
def test_without_a_repository_neither_a_file_nor_a_folder_gets_an_entry(provider, extension, monkeypatch, location):
    monkeypatch.setattr(extension, "repository_location", lambda source=None: location)

    assert provider.get_file_items([FileInfo("/home/ana/a.txt")]) == []
    assert provider.get_file_items([FileInfo("/home/ana/Docs", directory=True)]) == []
    assert provider.get_background_items(FileInfo("/home/ana/Docs", directory=True)) == []


def test_when_the_settings_cannot_be_read_the_entry_is_still_offered(provider, extension, monkeypatch):
    monkeypatch.setattr(extension, "repository_location", lambda source=None: None)
    assert len(provider.get_file_items([FileInfo("/home/ana/a.txt")])) == 1


def test_without_the_schema_the_location_is_unknown(extension):
    assert extension.repository_location(FakeSchemaSource(None)) is None


def test_a_file_in_the_home_folder_gets_the_menu_entry(provider):
    (entry,) = provider.get_file_items([FileInfo("/home/ana/Documents/report.odt")])
    assert entry.label == "Restore Previous Version…"
    assert entry.name == "Delta::RestorePreviousVersion"


def test_a_folder_in_the_home_folder_gets_the_menu_entry(provider):
    (entry,) = provider.get_file_items([FileInfo("/home/ana/Documents", directory=True)])
    assert entry.name == "Delta::RestorePreviousVersion"


def test_the_file_and_background_entries_have_different_names(provider):
    """Nautilus keys an entry's action by its name: a shared name made a photo open its folder."""
    (on_file,) = provider.get_file_items([FileInfo("/home/ana/Pictures/me.jpg")])
    (on_background,) = provider.get_background_items(FileInfo("/home/ana/Pictures", directory=True))

    assert on_file.name != on_background.name


def test_the_empty_space_of_a_folder_offers_that_folders_versions(provider, extension, monkeypatch):
    launched = []
    monkeypatch.setattr(extension, "launch_versions", launched.append)
    (entry,) = provider.get_background_items(FileInfo("/home/ana/Documents", directory=True))
    _, callback, args = entry.handlers[0]

    callback(entry, *args)

    assert launched == ["/home/ana/Documents"]


@pytest.mark.parametrize("folder", [None, FileInfo("/etc"), FileInfo("/home/analyst"), FileInfo(None)])
def test_no_entry_on_the_background_outside_the_home_folder(provider, folder):
    assert provider.get_background_items(folder) == []


@pytest.mark.parametrize("home", ["/home/ana", "/home/ana/"])
def test_the_empty_space_of_the_home_folder_offers_its_versions(provider, extension, monkeypatch, home):
    launched = []
    monkeypatch.setattr(extension, "launch_versions", launched.append)
    (entry,) = provider.get_background_items(FileInfo(home, directory=True))
    _, callback, args = entry.handlers[0]

    callback(entry, *args)

    assert launched == [home]


def test_older_nautilus_passing_the_window_first_still_works(provider):
    assert len(provider.get_file_items(object(), [FileInfo("/home/ana/a.txt")])) == 1


@pytest.mark.parametrize(
    "selection",
    [
        [],
        [FileInfo("/home/ana/a.txt"), FileInfo("/home/ana/b.txt")],
        [FileInfo("/home/ana/a.txt", scheme="sftp")],
        [FileInfo("/etc/passwd")],
        [FileInfo("/home/ana")],
        [FileInfo("/home/analyst/a.txt")],
        [FileInfo(None)],
    ],
)
def test_nothing_is_offered_where_a_restore_makes_no_sense(provider, selection):
    assert provider.get_file_items(selection) == []


def test_choosing_the_entry_opens_the_version_browser_for_that_file(provider, extension, monkeypatch):
    launched = []
    monkeypatch.setattr(extension, "launch_versions", launched.append)
    (entry,) = provider.get_file_items([FileInfo("/home/ana/a.txt")])
    signal, callback, args = entry.handlers[0]

    callback(entry, *args)

    assert signal == "activate" and launched == ["/home/ana/a.txt"]
