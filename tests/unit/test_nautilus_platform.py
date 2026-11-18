"""The extension's contact with the platform (settings, the daemon's bus name, the app launcher), stood in for."""

from types import SimpleNamespace

import pytest
from gi.repository import Gio, GLib
from test_nautilus_extension import extension  # noqa: F401  (the fixture that loads the module)


class GioWith:
    """Gio itself, except for the parts named: those are replaced."""

    def __init__(self, **parts):
        self._parts = parts

    def __getattr__(self, name):
        return self._parts[name] if name in self._parts else getattr(Gio, name)


def stand_in_gio(monkeypatch, extension, **parts):  # noqa: F811
    monkeypatch.setattr(extension, "Gio", GioWith(**parts))


class Stored:
    def __init__(self, location="/media/disk/delta-backups", sources=(), excludes=()):
        self.location, self.sources, self.excludes = location, list(sources), list(excludes)

    def get_string(self, key):
        return self.location

    def get_strv(self, key):
        return self.sources if key == "backup-sources" else self.excludes


def schemas(installed, stored):
    source = SimpleNamespace(lookup=lambda schema, recursive: object() if installed else None)
    return {
        "SettingsSchemaSource": SimpleNamespace(get_default=lambda: source),
        "Settings": SimpleNamespace(new_full=lambda schema, backend, path: stored),
    }


# --- the repository setting ----------------------------------------------------------------------


def test_the_repository_is_read_from_the_settings(extension, monkeypatch):  # noqa: F811
    stand_in_gio(monkeypatch, extension, **schemas(True, Stored("/media/disk/delta-backups")))

    assert extension.repository_location() == "/media/disk/delta-backups"


def test_without_the_schema_it_cannot_be_told(extension, monkeypatch):  # noqa: F811
    stand_in_gio(monkeypatch, extension, **schemas(False, Stored()))

    assert extension.repository_location() is None


def test_a_source_that_does_not_know_the_schema_means_it_cannot_be_told(extension):  # noqa: F811
    assert extension.repository_location(source=SimpleNamespace(lookup=lambda schema, recursive: None)) is None


def test_without_any_default_schema_source_it_cannot_be_told(extension, monkeypatch):  # noqa: F811
    stand_in_gio(monkeypatch, extension, SettingsSchemaSource=SimpleNamespace(get_default=lambda: None))

    assert extension.repository_location() is None


# --- the daemon ----------------------------------------------------------------------------------


def with_bus(monkeypatch, extension, call_sync):  # noqa: F811
    stand_in_gio(monkeypatch, extension, bus_get_sync=lambda bus, cancellable: SimpleNamespace(call_sync=call_sync))


def test_the_last_backup_is_asked_of_the_daemon_without_starting_it(extension, monkeypatch):  # noqa: F811
    asked = []

    def call_sync(name, path, interface, method, parameters, reply_type, flags, timeout, cancellable):
        asked.append((method, flags))
        return SimpleNamespace(unpack=lambda: (1_700_000_000,))

    with_bus(monkeypatch, extension, call_sync)

    assert extension._daemon_last_backup() == 1_700_000_000
    assert asked == [("Get", Gio.DBusCallFlags.NO_AUTO_START)]


def test_a_daemon_that_is_not_running_is_not_waited_for(extension, monkeypatch):  # noqa: F811
    def call_sync(*arguments):
        raise GLib.Error("no daemon", domain="test", code=1)

    with_bus(monkeypatch, extension, call_sync)

    assert extension._daemon_last_backup() is None


# --- what is known about the backup --------------------------------------------------------------


def test_the_backup_state_gathers_the_last_backup_and_what_is_chosen(extension, monkeypatch):  # noqa: F811
    stand_in_gio(monkeypatch, extension, **schemas(True, Stored(sources=["/home/ana/docs"], excludes=["/home/ana/tmp"])))
    monkeypatch.setattr(extension, "_daemon_last_backup", lambda: 1_700_000_000)

    info = extension.read_backup_state()

    assert (info.last_backup, info.sources, info.excludes) == (1_700_000_000, ("/home/ana/docs",), ("/home/ana/tmp",))


@pytest.mark.parametrize(
    ("installed", "location", "last"),
    [(False, "/media/disk/b", 1), (True, "", 1), (True, "/media/disk/b", None)],
    ids=["no settings", "no repository", "no daemon"],
)
def test_the_backup_state_is_unknown_when_any_part_is_missing(extension, monkeypatch, installed, location, last):  # noqa: F811
    stand_in_gio(monkeypatch, extension, **schemas(installed, Stored(location)))
    monkeypatch.setattr(extension, "_daemon_last_backup", lambda: last)

    assert extension.read_backup_state() is None


# --- opening the app -----------------------------------------------------------------------------


def with_launcher(monkeypatch, extension, info):  # noqa: F811
    stand_in_gio(monkeypatch, extension, DesktopAppInfo=SimpleNamespace(new=lambda desktop_id: info))


def test_the_versions_app_is_launched_with_the_file(extension, monkeypatch):  # noqa: F811
    launched = []
    with_launcher(monkeypatch, extension, SimpleNamespace(launch=lambda files, context: launched.append(files[0].get_path())))

    extension.launch_versions("/home/ana/a.txt")

    assert launched == ["/home/ana/a.txt"]


def test_a_missing_app_or_a_failed_launch_is_quietly_ignored(extension, monkeypatch):  # noqa: F811
    with_launcher(monkeypatch, extension, None)
    extension.launch_versions("/home/ana/a.txt")

    def refuse(files, context):
        raise GLib.Error("no display", domain="test", code=1)

    with_launcher(monkeypatch, extension, SimpleNamespace(launch=refuse))
    extension.launch_versions("/home/ana/a.txt")
