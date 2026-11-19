"""Widget tests: real GTK objects on whatever display the session has, built and driven but never shown.

They are skipped when GTK finds no display. Windows and dialogs are not presented and file choosers
are replaced, so nothing flashes on the desktop of whoever runs the tests.
"""

import time
from types import SimpleNamespace

import gi
import pytest

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk


@pytest.fixture(scope="session", autouse=True)
def display():
    if not Gtk.init_check():
        pytest.skip("GTK found no display")
    Adw.init()


@pytest.fixture(autouse=True)
def never_shown(monkeypatch):
    monkeypatch.setattr(Gtk.Window, "present", lambda self: None)
    monkeypatch.setattr(Adw.Dialog, "present", lambda self, parent=None: None)


def pump(until, seconds=3.0):
    """Run the main context until `until()` holds, as a window's own loop would."""
    context, deadline = GLib.MainContext.default(), time.monotonic() + seconds
    while not until() and time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)
    return until()


class FakeClient:
    """Stands in for DeltaClient: remembers each request and lets the test answer it."""

    def __init__(self):
        self.requests = []  # (method, arguments, reply)
        self.subscriptions = {}
        self.unsubscribed = []

    def __getattr__(self, method):
        if method.startswith("on_"):

            def subscribe(handler):
                self.subscriptions[method] = handler
                return len(self.subscriptions)

            return subscribe

        def request(*arguments):
            reply = arguments[-1] if arguments and callable(arguments[-1]) else None
            self.requests.append((method, arguments[:-1] if reply else arguments, reply))

        return request

    def unsubscribe(self, subscription):
        self.unsubscribed.append(subscription)

    def asked(self, method):
        return [arguments for name, arguments, _reply in self.requests if name == method]

    def answer(self, method, *reply_arguments):
        """Answer the latest request of `method`."""
        reply = [reply for name, _arguments, reply in self.requests if name == method][-1]
        reply(*reply_arguments)


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def dialogs(monkeypatch):
    """Adw.AlertDialog.choose is recorded instead of shown; `respond(answer)` answers the latest."""
    shown = SimpleNamespace(items=[], answer="cancel")

    def choose(self, parent, cancellable, callback):
        shown.items.append((self, callback))

    def respond(answer):
        shown.answer = answer
        dialog, callback = shown.items[-1]
        callback(dialog, None)

    monkeypatch.setattr(Adw.AlertDialog, "choose", choose)
    monkeypatch.setattr(Adw.AlertDialog, "choose_finish", lambda self, result: shown.answer)
    shown.respond = respond
    return shown
