import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

from delta.infrastructure.gio_notifier import OPEN_ACTION, GioNotifier


def application():
    return Gio.Application.new("io.github.sincorchetes.Delta.NotifierTest", Gio.ApplicationFlags.DEFAULT_FLAGS)


def test_clicking_a_notification_opens_the_app_through_the_apps_action():
    app, opened = application(), []
    GioNotifier(app, lambda: opened.append(True))

    action = app.lookup_action(OPEN_ACTION)
    assert action is not None
    action.activate(None)

    assert opened == [True]


def test_without_an_opener_no_action_is_registered():
    app = application()
    GioNotifier(app)
    assert app.lookup_action(OPEN_ACTION) is None
