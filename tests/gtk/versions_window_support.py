"""What the tests of the versions window share."""

import time
import pytest
from gtk_helpers import of_type, started_application
from gi.repository import Gtk
from delta.ui import version_preview, versions_window
from delta.ui.versions_window import VersionsWindow


OLD = 1_700_000_000


@pytest.fixture
def app():
    return started_application("DeltaVersionsTests")


@pytest.fixture
def note(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("today")
    return path


@pytest.fixture
def unpacked(tmp_path):
    path = tmp_path / "unpacked" / "note.txt"
    path.parent.mkdir()
    path.write_text("what it said before")
    return path


@pytest.fixture
def folder(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "inside.txt").write_text("hello")
    (root / "sub").mkdir()
    return root


def file_versions():
    now = int(time.time())
    return [
        {"name": "s2", "time": now - 60, "mtime": OLD + 100, "size": 12, "is_dir": False},
        {"name": "s1", "time": now - 3600, "mtime": OLD, "size": 10, "is_dir": False},
    ]


def folder_versions():
    return [{**row, "is_dir": True} for row in file_versions()]


def listing():
    return [
        {"name": "inside.txt", "is_dir": False, "size": 5, "mtime": OLD},
        {"name": "gone.txt", "is_dir": False, "size": 9, "mtime": OLD},
        {"name": "sub", "is_dir": True, "size": 0, "mtime": OLD},
    ]


def open_window(app, client, path):
    window = VersionsWindow(app, client, str(path))
    window.toasts = []
    window._toasts.add_toast = window.toasts.append
    return window


def finish_preview(client, unpacked, job="preview"):
    client.answer("preview_version", job, None)
    client.subscriptions["on_backup_finished"](job, True, str(unpacked))


class Launcher:
    launched = []

    def __init__(self, gfile):
        self.gfile = gfile

    @classmethod
    def new(cls, gfile):
        return cls(gfile)

    def launch(self, window, cancellable, callback):
        Launcher.launched.append(("launch", self.gfile.get_path()))

    def open_containing_folder(self, window, cancellable, callback):
        Launcher.launched.append(("containing", self.gfile.get_path()))


class GtkWithOurLauncher:
    """Gtk, except that nothing is ever handed to the desktop: the launcher only takes notes."""

    FileLauncher = Launcher

    def __getattr__(self, name):
        return getattr(Gtk, name)


@pytest.fixture
def launcher(monkeypatch):
    Launcher.launched = []
    monkeypatch.setattr(version_preview, "Gtk", GtkWithOurLauncher())
    monkeypatch.setattr(versions_window, "Gtk", GtkWithOurLauncher())
    return Launcher


def row_named(window, name):
    names = [row.name for row in window._browser._shown]
    return window._browser._list.get_row_at_index(names.index(name))


def revert_button(row):
    return next(b for b in of_type(row, Gtk.Button) if b.get_icon_name() == "document-revert-symbolic")


@pytest.fixture
def viewing(app, client, note, unpacked):
    window = open_window(app, client, note)
    client.answer("list_versions", file_versions(), None)
    finish_preview(client, unpacked)
    return window


@pytest.fixture
def browsing(app, client, folder):
    window = open_window(app, client, folder)
    client.answer("list_versions", folder_versions(), None)
    client.answer("list_folder", listing(), None)
    return window
