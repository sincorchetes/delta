"""What the tests of test_folder_browser share."""

import os
import pytest
from gtk_helpers import of_type
from gi.repository import Gtk
from delta.ui.folder_browser import FolderBrowser


OLD = 1_700_000_000


@pytest.fixture
def root(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    same = folder / "same.txt"
    same.write_text("hello")
    os.utime(same, (OLD, OLD))
    (folder / "changed.txt").write_text("now it is longer")
    (folder / "sub").mkdir()
    return folder


def backed_up():
    """Folders first, then by name: sub, changed.txt, gone.txt, same.txt."""
    return [
        {"name": "same.txt", "is_dir": False, "size": 5, "mtime": OLD},
        {"name": "changed.txt", "is_dir": False, "size": 3, "mtime": OLD},
        {"name": "gone.txt", "is_dir": False, "size": 9, "mtime": OLD},
        {"name": "sub", "is_dir": True, "size": 0, "mtime": OLD},
    ]


class Harness:
    def __init__(self, client, root):
        self.client, self.root = client, str(root)
        self.files, self.changes, self.restores, self.deleted = [], 0, [], 0
        self.browser = FolderBrowser(
            client,
            lambda path, size: self.files.append((path, size)),
            self._changed,
            lambda paths, in_place: self.restores.append((paths, in_place)),
            lambda: setattr(self, "deleted", self.deleted + 1),
        )

    def _changed(self):
        self.changes += 1

    def names(self):
        return [row.name for row in self.browser._shown]

    def row(self, name):
        return self.browser._list.get_row_at_index(self.names().index(name))

    def visible(self):
        return self.browser._stack.get_visible_child_name()


@pytest.fixture
def harness(client, root):
    seen = Harness(client, root)
    yield seen
    seen.browser.close()


@pytest.fixture
def opened(harness, client):
    harness.browser.open("snap", harness.root)
    client.answer("list_folder", backed_up(), None)
    return harness


def restore_button(row):
    return next(b for b in of_type(row, Gtk.Button) if b.get_icon_name() == "document-revert-symbolic")
