"""What the tests of the status window share."""

import time
from types import SimpleNamespace
import pytest
from gtk_helpers import started_application
from gi.repository import Adw
from delta.ui.application import DeltaApplication
from delta.ui.window import StatusWindow


class Settings:
    def __init__(self, repository="/media/disk/delta-backups", schedule="hourly"):
        self.values = {"repository-location": repository, "schedule": schedule}
        self.callbacks = []

    def get_string(self, key):
        return self.values[key]

    def connect(self, signal, callback):
        self.callbacks.append((signal, callback))


class Recorder:
    """Stands in for a window class: remembers how it was built and shown."""

    built = []

    def __init__(self, *arguments):
        self.arguments, self.shown = arguments, 0
        Recorder.built.append(self)

    def present(self, parent=None):
        self.shown += 1


@pytest.fixture(autouse=True)
def fresh_recorder():
    Recorder.built = []


@pytest.fixture
def app():
    return started_application("DeltaTests")


def open_window(app, client, settings=None, with_settings=True):
    settings = (settings or Settings()) if with_settings else None
    window = StatusWindow(app, client, settings)
    toasts = []
    window._toasts.add_toast = toasts.append
    return window, settings, toasts


def tell(client, **properties):
    client.answer("read_state", properties, None)


def protected(**extra):
    now = int(time.time())
    return {"Status": "idle", "LastBackup": now - 60, "NextBackup": now + 1800, "LastError": "", **extra}


class CommandLine:
    def __init__(self, versions=None, target="/home/u/a.txt"):
        self.versions, self.target = versions, target

    def get_options_dict(self):
        options = {"versions": self.versions} if self.versions is not None else {}
        return SimpleNamespace(end=lambda: SimpleNamespace(unpack=lambda: options))

    def create_file_for_arg(self, path):
        return SimpleNamespace(get_path=lambda: self.target)


@pytest.fixture
def delta_app(monkeypatch, client):
    instance = DeltaApplication()
    monkeypatch.setattr(instance, "_client_for_session", lambda: client)
    return instance


@pytest.fixture
def alerts(monkeypatch):
    """Adw.AlertDialog.present is recorded instead of shown: (heading, body, responses)."""
    shown = []
    monkeypatch.setattr(
        Adw.AlertDialog,
        "present",
        lambda self, parent=None: shown.append((self.get_heading(), self.get_body(), self.has_response("close"))),
    )
    return shown


def check_action(window):
    return window.lookup_action("check")
