"""The extension runs inside Nautilus, so it is loaded here against a stand-in for Nautilus."""

import gettext
import importlib.util
import sys
import time
import types
from pathlib import Path

import gi
import pytest
from gi import repository

EXTENSION = Path(__file__).resolve().parents[2] / "src" / "nautilus" / "delta_extension.py"


class FakeMenuItem:
    def __init__(self, name, label):
        self.name, self.label, self.handlers = name, label, []

    def connect(self, signal, callback, *args):
        self.handlers.append((signal, callback, args))


class FakeColumn:
    def __init__(self, name, attribute, label, description):
        self.name, self.attribute, self.label, self.description = name, attribute, label, description


@pytest.fixture
def extension(monkeypatch):
    nautilus = types.ModuleType("Nautilus")
    nautilus.MenuProvider = type("MenuProvider", (), {})
    nautilus.InfoProvider = type("InfoProvider", (), {})
    nautilus.ColumnProvider = type("ColumnProvider", (), {})
    nautilus.MenuItem = FakeMenuItem
    nautilus.Column = FakeColumn
    real = gi.require_version
    monkeypatch.setattr(
        gi, "require_version", lambda name, version: None if name == "Nautilus" else real(name, version)
    )
    monkeypatch.setitem(sys.modules, "gi.repository.Nautilus", nautilus)
    monkeypatch.setattr(repository, "Nautilus", nautilus, raising=False)
    spec = importlib.util.spec_from_file_location("delta_extension_under_test", EXTENSION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Location:
    def __init__(self, path):
        self._path = path

    def get_path(self):
        return self._path


class FileInfo:
    def __init__(self, path, directory=False, scheme="file"):
        self._path, self._directory, self._scheme = path, directory, scheme
        self.attributes, self.emblems = {}, []

    def add_string_attribute(self, name, value):
        self.attributes[name] = value

    def add_emblem(self, name):
        self.emblems.append(name)

    def is_directory(self):
        return self._directory

    def get_uri_scheme(self):
        return self._scheme

    def get_location(self):
        return Location(self._path)


@pytest.fixture
def provider(extension, monkeypatch):
    monkeypatch.setattr(extension.GLib, "get_home_dir", lambda: "/home/ana")
    monkeypatch.setattr(extension, "repository_location", lambda source=None: "/run/media/ana/Disk/delta-backups")
    return extension.DeltaMenuProvider()


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


class FakeSchemaSource:
    def __init__(self, schema=None):
        self._schema = schema

    def lookup(self, schema_id, recursive):
        return self._schema if schema_id == "io.github.sincorchetes.Delta" else None


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


@pytest.mark.parametrize("folder", [None, FileInfo("/home/ana"), FileInfo("/etc"), FileInfo(None)])
def test_no_entry_on_the_background_of_home_or_outside_it(provider, folder):
    assert provider.get_background_items(folder) == []


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


def test_the_menu_text_is_translated_from_a_data_directory(extension, tmp_path):
    catalogue = tmp_path / "locale" / "es" / "LC_MESSAGES"
    catalogue.mkdir(parents=True)
    mo = _compile(catalogue, {"Restore Previous Version…": "Restaurar versión anterior…"})
    assert mo.exists()

    found = extension.translations([str(tmp_path)], languages=["es"])

    assert found.gettext("Restore Previous Version…") == "Restaurar versión anterior…"


def test_a_flatpak_install_is_looked_at_for_the_catalogue_after_the_system_ones(extension, tmp_path):
    dirs = extension.flatpak_share_dirs(str(tmp_path))

    assert dirs == [
        f"{tmp_path}/flatpak/app/io.github.sincorchetes.Delta/current/active/files/share",
        "/var/lib/flatpak/app/io.github.sincorchetes.Delta/current/active/files/share",
    ]


def test_the_menu_text_is_translated_from_a_flatpak_install_that_nautilus_can_read(extension, tmp_path):
    share = tmp_path / "flatpak" / "app" / "io.github.sincorchetes.Delta" / "current" / "active" / "files" / "share"
    catalogue = share / "locale" / "es" / "LC_MESSAGES"
    catalogue.mkdir(parents=True)
    _compile(catalogue, {"Restore Previous Version…": "Restaurar versión anterior…"})

    found = extension.translations(extension.flatpak_share_dirs(str(tmp_path)), languages=["es"])

    assert found.gettext("Restore Previous Version…") == "Restaurar versión anterior…"


def test_by_default_the_flatpak_folders_are_searched_too(extension, monkeypatch):
    asked = []

    def nothing_here(domain, localedir, languages=None):
        asked.append(localedir)
        raise OSError

    monkeypatch.setattr(extension.gettext, "translation", nothing_here)

    extension.translations(languages=["es"])

    assert any("/flatpak/app/io.github.sincorchetes.Delta/" in path for path in asked)


def test_without_any_catalogue_the_text_stays_in_english(extension, tmp_path):
    found = extension.translations([str(tmp_path)], languages=["es"])
    assert isinstance(found, gettext.NullTranslations)
    assert found.gettext("Restore Previous Version…") == "Restore Previous Version…"


def test_the_extension_never_imports_the_delta_package():
    """Nautilus runs it with a different interpreter, where `delta` is not importable."""
    source = EXTENSION.read_text(encoding="utf-8")
    assert "import delta" not in source and "from delta" not in source


def _compile(folder: Path, messages: dict) -> Path:
    """Write a minimal .mo file (no msgfmt needed): that is what gettext reads."""
    import struct

    pairs = sorted({"": "Content-Type: text/plain; charset=UTF-8\n", **messages}.items())
    ids = b"\0".join(key.encode() for key, _ in pairs) + b"\0"
    strings = b"\0".join(value.encode() for _, value in pairs) + b"\0"
    count, table = len(pairs), 7 * 4
    id_offsets, string_offsets, position = [], [], table + count * 16
    for key, _ in pairs:
        id_offsets.append((len(key.encode()), position))
        position += len(key.encode()) + 1
    for _, value in pairs:
        string_offsets.append((len(value.encode()), position))
        position += len(value.encode()) + 1
    data = struct.pack("<7I", 0x950412DE, 0, count, table, table + count * 8, 0, 0)
    data += b"".join(struct.pack("<2I", *item) for item in id_offsets)
    data += b"".join(struct.pack("<2I", *item) for item in string_offsets)
    mo = folder / "delta.mo"
    mo.write_bytes(data + ids + strings)
    return mo


def test_without_any_gtk4_nautilus_api_loading_fails_clearly(monkeypatch):
    def refuse(name, version):
        if name == "Nautilus":
            raise ValueError("Namespace Nautilus not available")

    monkeypatch.setattr(gi, "require_version", refuse)
    spec = importlib.util.spec_from_file_location("delta_extension_missing_api", EXTENSION)
    module = importlib.util.module_from_spec(spec)
    with pytest.raises(ImportError, match="Nautilus-4"):
        spec.loader.exec_module(module)


def test_the_newest_api_version_is_tried_first(monkeypatch, extension):
    asked = []
    nautilus = sys.modules["gi.repository.Nautilus"]
    monkeypatch.setattr(gi, "require_version", lambda name, version: asked.append((name, version)))
    spec = importlib.util.spec_from_file_location("delta_extension_order", EXTENSION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert asked[0] == ("Nautilus", "4.1") and nautilus is not None


# --- the backup state of each file: a column, and an emblem on what changed -------------------

HOME = "/home/ana"


def backup_info(extension, last=1000, sources=(), excludes=()):
    return extension.BackupInfo(last, tuple(sources), tuple(excludes))


@pytest.mark.parametrize(
    ("path", "sources", "excludes", "covered"),
    [
        ("/home/ana/Documents/a.txt", (), (), True),  # no folders chosen: the whole home folder
        ("/home/ana/.cache/x/y", (), (), False),  # what the daemon never backs up
        ("/home/ana/.local/share/Trash/files/old", (), (), False),
        ("/home/ana/Pictures/me.jpg", ("~/Pictures",), (), True),
        ("/home/ana/Documents/a.txt", ("~/Pictures",), (), False),  # outside the chosen folders
        ("/home/ana/Picturesque/a.txt", ("~/Pictures",), (), False),  # a sibling, not inside
        ("/home/ana/Pictures/Screenshots/a.png", ("~/Pictures",), ("/home/ana/Pictures/Screenshots",), False),
        ("/home/ana/Pictures/Screenshots/a.png", ("~/Pictures",), ("~/Pictures/Screenshots",), False),
        ("/home/ana/Pictures/ScreenshotsOld/a.png", ("~/Pictures",), ("~/Pictures/Screenshots",), True),
        ("/home/ana/Documents/a.txt", ("relative/dir",), (), True),  # an invalid source is dropped
    ],
)
def test_the_backup_covers_the_chosen_folders_minus_the_skipped_ones(extension, path, sources, excludes, covered):
    assert extension.is_covered(path, HOME, backup_info(extension, sources=sources, excludes=excludes)) is covered


def test_a_file_unchanged_since_the_last_backup_is_saved(extension):
    info = backup_info(extension, last=1000)
    assert extension.backup_status("/home/ana/a.txt", 900, info, HOME) == extension.SAVED
    assert extension.backup_status("/home/ana/a.txt", 1000.4, info, HOME) == extension.SAVED


def test_a_file_changed_after_the_last_backup_is_pending(extension):
    assert extension.backup_status("/home/ana/a.txt", 1001, backup_info(extension, last=1000), HOME) == extension.PENDING


def test_before_the_first_backup_everything_covered_is_pending(extension):
    assert extension.backup_status("/home/ana/a.txt", 5, backup_info(extension, last=0), HOME) == extension.PENDING


def test_a_file_the_backup_skips_has_no_state(extension):
    assert extension.backup_status("/home/ana/.cache/a", 5, backup_info(extension), HOME) is None


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_the_state_is_read_once_per_refresh_period_not_once_per_file(extension):
    reads, clock = [], FakeClock()
    state = extension.BackupState(read=lambda: reads.append(1) or backup_info(extension), clock=clock)

    for _ in range(50):  # Nautilus asks for every visible file
        state.get()
    assert len(reads) == 1

    clock.now += extension.REFRESH_SECONDS - 1
    state.get()
    assert len(reads) == 1

    clock.now += 1
    state.get()
    assert len(reads) == 2


def test_an_unknown_state_is_kept_for_the_period_too(extension):
    reads, clock = [], FakeClock()
    state = extension.BackupState(read=lambda: reads.append(1), clock=clock)  # always None
    state.get()
    state.get()
    assert len(reads) == 1


class FakeState:
    def __init__(self, info):
        self._info = info

    def get(self):
        return self._info


@pytest.fixture
def home(tmp_path, extension, monkeypatch):
    monkeypatch.setattr(extension.GLib, "get_home_dir", lambda: str(tmp_path))
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Documents" / "a.txt").write_text("x")
    return tmp_path


def info_for(extension, info):
    return extension.DeltaInfoProvider(state=FakeState(info))


def test_there_is_one_backup_column(extension):
    (column,) = info_for(extension, None).get_columns()
    assert column.attribute == "delta_backup" and column.name == "Delta::Backup"
    assert column.label == "Backup"


def test_a_file_changed_since_the_last_backup_gets_the_emblem_and_the_column_text(extension, home):
    file = FileInfo(str(home / "Documents" / "a.txt"))

    info_for(extension, backup_info(extension, last=1)).update_file_info(file)

    assert file.attributes == {"delta_backup": "Changed since the last backup"}
    assert file.emblems == [extension.PENDING_EMBLEM]


def test_a_saved_file_only_gets_the_column_text(extension, home):
    file = FileInfo(str(home / "Documents" / "a.txt"))
    future = int(time.time()) + 1000

    info_for(extension, backup_info(extension, last=future)).update_file_info(file)

    assert file.attributes == {"delta_backup": "In the latest backup"}
    assert file.emblems == []


@pytest.mark.parametrize(
    "build",
    [
        lambda home: FileInfo(str(home / "Documents"), directory=True),
        lambda home: FileInfo(str(home / "Documents" / "a.txt"), scheme="sftp"),
        lambda home: FileInfo("/etc/passwd"),
        lambda home: FileInfo(str(home / "Documents" / "missing.txt")),
        lambda home: FileInfo(None),
    ],
    ids=["folder", "not a local file", "outside home", "vanished", "no path"],
)
def test_things_with_no_file_state_are_left_alone(extension, home, build):
    file = build(home)

    info_for(extension, backup_info(extension, last=1)).update_file_info(file)

    assert file.attributes == {} and file.emblems == []


def test_when_the_state_is_unknown_nothing_is_marked(extension, home):
    """No repository, no settings or the daemon is not running: say nothing rather than guess."""
    file = FileInfo(str(home / "Documents" / "a.txt"))

    info_for(extension, None).update_file_info(file)

    assert file.attributes == {} and file.emblems == []


def test_a_skipped_folder_is_not_marked(extension, home):
    cache = home / ".cache"
    cache.mkdir()
    (cache / "x").write_text("x")
    file = FileInfo(str(cache / "x"))

    info_for(extension, backup_info(extension, last=1)).update_file_info(file)

    assert file.attributes == {} and file.emblems == []
