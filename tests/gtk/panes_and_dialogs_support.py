"""What the tests of the panes and dialogs share."""

import base64
import wave
from types import SimpleNamespace
import pytest
from gtk_helpers import of_type
from gi.repository import Gtk
from delta.ui.job_tracker import JobTracker
from delta.ui.preferences_dialog import PreferencesDialog
from delta.ui.preview_pane import PreviewPane
from delta.ui.restore_deleted import RestoreDeleted


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@pytest.fixture
def pane():
    return PreviewPane()


def silence(path):
    """A real, valid audio file: a tenth of a second of nothing."""
    with wave.open(str(path), "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(8000)
        sound.writeframes(b"\x00\x00" * 800)
    return path


class Settings:
    def __init__(self, **values):
        self.values = {
            "repository-location": "/media/disk/delta-backups",
            "schedule": "hourly",
            "keep-hourly": 24,
            "keep-daily": 7,
            "keep-weekly": 4,
            "keep-monthly": 12,
            "backup-sources": [],
            "excluded-paths": [],
        }
        self.values.update(values)
        self.written = []

    def get_string(self, key):
        return self.values[key]

    get_int = get_strv = get_string

    def _set(self, key, value):
        self.written.append((key, value))
        self.values[key] = value

    set_string = set_int = set_strv = _set


def preferences(client=None, **values):
    settings = Settings(**values)
    dialog = PreferencesDialog(settings, "/home/u", None, client)
    toasts = []
    dialog.add_toast = toasts.append
    return dialog, settings, toasts


def checks(dialog):
    return of_type(dialog.get_visible_page(), Gtk.CheckButton)


@pytest.fixture
def restoring(client):
    seen = SimpleNamespace(toasts=[], changes=0, done=0)
    tracker = JobTracker()
    flow = RestoreDeleted(
        client,
        tracker,
        None,
        seen.toasts.append,
        lambda: setattr(seen, "changes", seen.changes + 1),
        lambda: setattr(seen, "done", seen.done + 1),
    )
    seen.flow, seen.tracker = flow, tracker
    return seen


def rows(n):
    return [{"name": f"f{i}", "size": 1000, "is_dir": False, "mtime": 1} for i in range(n)]
