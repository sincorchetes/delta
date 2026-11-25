"""What the tests of the small widgets share."""

from types import SimpleNamespace
import pytest
from gtk_helpers import of_type
from gi.repository import GLib, Gtk
from delta.ui import wizard_base, wizard_destination
from delta.ui.folder_listing import Change, FolderRow
from delta.ui.path_list import PathListGroup
from delta.ui.timeline import Timeline
from delta.ui.versions import VersionRow
from delta.ui.wizard import WizardModel
from delta.ui.wizard_destination import DestinationPage


def version(n):
    return VersionRow(snapshot=f"s{n}", modified=f"2026-01-0{n}", backed_up=f"Backed up {n}", size=n)


@pytest.fixture
def chosen():
    return []


@pytest.fixture
def opened():
    return []


@pytest.fixture
def line(chosen, opened):
    widget = Timeline(chosen.append, lambda: opened.append(True))
    widget.fill([version(3), version(2), version(1)])
    return widget


def entry(change=Change.MODIFIED, is_dir=False, name="photo.jpg"):
    return FolderRow(name=name, is_dir=is_dir, size=10, mtime=1, detail="10 bytes", change=change)


def restore_button(row):
    return next(b for b in of_type(row, Gtk.Button) if b.get_icon_name() == "document-revert-symbolic")


class Dialog:
    last = None

    def __init__(self, title):
        self.title, self.callback, self.initial = title, None, None
        Dialog.last = self

    def set_initial_folder(self, folder):
        self.initial = folder.get_path()

    def select_folder(self, window, cancellable, callback):
        self.callback = callback

    def open(self, window, cancellable, callback):
        self.callback = callback

    def select_folder_finish(self, result):
        if isinstance(result, GLib.Error):
            raise result
        return result

    open_finish = select_folder_finish


@pytest.fixture
def file_dialog(monkeypatch):
    monkeypatch.setattr(wizard_base, "Gtk", SimpleNamespace(FileDialog=Dialog))
    return Dialog


def Drive():
    return SimpleNamespace(
        name="Backup disk", mount_point="/run/media/u/disk", suggested_folder="/run/media/u/disk/delta-backups"
    )


def destination_page(monkeypatch, drives=()):
    monkeypatch.setattr(wizard_destination, "removable_drives", lambda mounts: list(drives))
    model = WizardModel(home="/home/u", inspect=lambda path: None)
    changes = []
    return DestinationPage(model, None, lambda: changes.append(model.destination)), model, changes


@pytest.fixture
def paths():
    seen = SimpleNamespace(changed=[], problems=[])
    seen.group = PathListGroup(
        None,
        "Folders",
        "Which folders",
        "Nothing chosen",
        seen.changed.append,
        seen.problems.append,
        allow_files=True,
        check=lambda path: "Not allowed" if path == "/etc" else None,
    )
    return seen
