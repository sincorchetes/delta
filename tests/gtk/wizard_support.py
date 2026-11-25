"""What the tests of the setup wizard share."""

from types import SimpleNamespace
import pytest
from gi.repository import GLib
from delta.ui.wizard import PathState, Step, WizardModel
from delta.ui.wizard_pages import FoldersPage, RecoveryPage, SummaryPage
from delta.ui.wizard_window import SetupWizard


HOME = "/home/u"


def model(**fields):
    return WizardModel(home=HOME, inspect=lambda path: PathState.MISSING, recovery_key="AAAAA-BBBBB", **fields)


def folders_page(**fields):
    chosen = model(**fields)
    changes = []
    return FoldersPage(chosen, None, lambda: changes.append(chosen.folders)), chosen, changes


class Clipboard:
    def __init__(self):
        self.content = None

    def set_content(self, provider):
        self.content = provider


def recovery_page():
    chosen = model()
    changes = []
    page = RecoveryPage(chosen, None, lambda: changes.append(True))
    page.clipboard = Clipboard()
    page.get_clipboard = lambda: page.clipboard
    return page, chosen, changes


class SaveDialog:
    def __init__(self, title, initial_name):
        self.title, self.initial_name = title, initial_name
        self.callback = None

    def save(self, window, cancellable, callback):
        self.callback = callback

    def save_finish(self, result):
        if isinstance(result, GLib.Error):
            raise result
        return result


def summary_page():
    chosen = model(destination="/media/disk/delta-backups", recovery_saved=True)
    return SummaryPage(chosen, None, lambda: None), chosen


class Settings:
    def __init__(self):
        self.written = []

    @staticmethod
    def get_string(key):
        return "/media/current/delta"

    def set_strv(self, key, value):
        self.written.append((key, value))


@pytest.fixture
def setup(client, tmp_path):
    seen = SimpleNamespace(done=0, settings=Settings(), client=client)
    seen.wizard = SetupWizard(None, client, seen.settings, lambda: setattr(seen, "done", seen.done + 1))
    seen.destination = str(tmp_path / "delta-backups")
    return seen


def go_to_the_summary(seen):
    seen.wizard._model.destination = seen.destination
    seen.wizard._model.recovery_saved = True
    for _step in range(3):
        seen.wizard._on_next(None)
    assert seen.wizard._model.step is Step.SUMMARY


@pytest.fixture
def change(client, tmp_path):
    seen = SimpleNamespace(done=0, settings=Settings(), client=client)
    seen.wizard = SetupWizard(None, client, seen.settings, lambda: setattr(seen, "done", seen.done + 1), change=True)
    seen.destination = str(tmp_path / "other-drive")
    return seen
