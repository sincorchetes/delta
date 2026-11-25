"""The application around the status window: help, the menu, the command line and main."""

from types import SimpleNamespace
import pytest
from gtk_helpers import of_type
from gi.repository import Gtk
from delta.ui import application as application_module
from delta.ui.application import DeltaApplication, main
from status_window_support import CommandLine, Recorder, open_window
from status_window_support import app, delta_app, fresh_recorder  # noqa: F401  (fixtures)


def test_help_opens_the_manual_in_yelp_from_its_action_and_from_f1(delta_app, monkeypatch):
    opened = []

    class Launcher:
        @staticmethod
        def new(uri):
            return SimpleNamespace(launch=lambda parent, cancellable, callback: opened.append((uri, parent)))

    monkeypatch.setattr(application_module, "Gtk", SimpleNamespace(UriLauncher=Launcher))
    monkeypatch.setattr(application_module, "in_flatpak", lambda: False)
    monkeypatch.setattr(application_module, "manual_installed", lambda: True)
    monkeypatch.setattr(application_module, "has_viewer", lambda: True)
    monkeypatch.setattr(delta_app, "get_active_window", lambda: "the window")

    delta_app.lookup_action("help").activate(None)  # activate_action needs a registered application

    assert opened == [("help:delta", "the window")]
    assert delta_app.get_accels_for_action("app.help") == ["F1"]


@pytest.mark.parametrize(
    ("sandboxed", "manual", "viewer"),
    [
        (True, True, True),  # a Flatpak: Yelp cannot read the sandbox
        (False, False, True),  # the install does not link the manual
        (False, True, False),  # nothing is registered for help: addresses
    ],
)
def test_when_the_manual_cannot_be_opened_here_the_help_is_the_web(delta_app, monkeypatch, sandboxed, manual, viewer):
    opened = []
    launcher = SimpleNamespace(new=lambda uri: SimpleNamespace(launch=lambda *args: opened.append(uri)))
    monkeypatch.setattr(application_module, "Gtk", SimpleNamespace(UriLauncher=launcher))
    monkeypatch.setattr(application_module, "in_flatpak", lambda: sandboxed)
    monkeypatch.setattr(application_module, "manual_installed", lambda: manual)
    monkeypatch.setattr(application_module, "has_viewer", lambda: viewer)

    delta_app.show_help()

    assert opened == ["https://delta.sincorchetes.tech"]


def test_the_main_menu_offers_preferences_help_and_about(app, client):
    window, _settings, _toasts = open_window(app, client)
    model = of_type(window, Gtk.MenuButton)[0].get_menu_model()

    entries = [
        (
            model.get_item_attribute_value(i, "label").get_string(),
            model.get_item_attribute_value(i, "action").get_string(),
        )
        for i in range(model.get_n_items())
    ]

    assert entries == [
        ("Check backups", "win.check"),
        ("Preferences", "win.preferences"),
        ("Help", "app.help"),
        ("About Delta", "win.about"),
    ]


def test_without_options_the_status_window_is_shown(delta_app, monkeypatch):
    activated = []
    monkeypatch.setattr(delta_app, "activate", lambda: activated.append(True))

    assert delta_app.do_command_line(CommandLine()) == 0 and activated == [True]


def test_asking_for_versions_opens_that_files_window(delta_app, client, monkeypatch):
    monkeypatch.setattr(application_module, "VersionsWindow", Recorder)

    status = delta_app.do_command_line(CommandLine(versions=b"/home/u/a.txt\0"))

    assert status == 0 and Recorder.built[0].arguments == (delta_app, client, "/home/u/a.txt")
    assert Recorder.built[0].shown == 1


def test_a_filename_option_arrives_from_glib_as_a_list_of_bytes(delta_app, client, monkeypatch):
    monkeypatch.setattr(application_module, "VersionsWindow", Recorder)

    delta_app.do_command_line(CommandLine(versions=list(b"/home/u/a.txt\0")))

    assert Recorder.built[0].arguments[2] == "/home/u/a.txt"


def test_a_versions_path_that_is_not_a_local_file_is_an_error(delta_app, monkeypatch):
    monkeypatch.setattr(application_module, "VersionsWindow", Recorder)

    assert delta_app.do_command_line(CommandLine(versions=b"https://x\0", target=None)) == 1
    assert Recorder.built == []


def test_activating_twice_shows_the_same_window_and_a_closed_one_is_forgotten(delta_app, monkeypatch):
    class Window(Recorder):
        def connect(self, signal, callback):
            self.callback = callback

    monkeypatch.setattr(application_module, "StatusWindow", Window)
    monkeypatch.setattr(application_module, "open_settings", lambda: None)

    delta_app.do_activate()
    delta_app.do_activate()
    assert len(Recorder.built) == 1 and Recorder.built[0].shown == 2

    Recorder.built[0].callback(Recorder.built[0])
    assert delta_app._status is None


def test_the_client_is_made_once_from_the_session_bus(monkeypatch):
    app_with_bus = DeltaApplication()
    connections = []
    monkeypatch.setattr(
        application_module,
        "Gio",
        SimpleNamespace(
            BusType=SimpleNamespace(SESSION=0), bus_get_sync=lambda bus, cancellable: connections.append(1) or object()
        ),
    )

    first = app_with_bus._client_for_session()

    assert app_with_bus._client_for_session() is first and connections == [1]


def test_main_sets_up_translations_and_runs_the_application(monkeypatch):
    steps = []
    monkeypatch.setattr(application_module.i18n, "setup", lambda: steps.append("i18n"))
    monkeypatch.setattr(application_module, "DeltaApplication", lambda: SimpleNamespace(run=lambda argv: 5))

    assert main() == 5 and steps == ["i18n"]
