"""The status window and the application around it, driven through a stand-in daemon client."""

import time
from types import SimpleNamespace

import pytest
from gtk_helpers import of_type
from gi.repository import Adw, Gio, GLib, Gtk

from delta.ui import application as application_module
from delta.ui import window as window_module
from delta.ui.application import DeltaApplication, main
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
    application = Adw.Application(application_id="io.github.sincorchetes.DeltaTests", flags=Gio.ApplicationFlags.NON_UNIQUE)
    application.register(None)  # emits `startup`: GTK complains about a window of an application that has not started
    return application


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


# --- what the window says ------------------------------------------------------------------------


def test_asking_the_daemon_is_the_first_thing_the_window_does(app, client):
    open_window(app, client)

    assert len(client.asked("read_state")) == 1


def test_a_healthy_setup_says_so_and_offers_to_back_up_now(app, client):
    window, _settings, _toasts = open_window(app, client)

    tell(client, **protected())

    assert window._page.get_title() == "Your files are protected"
    assert window._button.get_label() == "Back up now" and window._button.get_visible()
    assert window._history.get_sensitive()


def test_without_a_repository_the_button_sets_backups_up(app, client, monkeypatch):
    monkeypatch.setattr(window_module, "SetupWizard", Recorder)
    window, settings, _toasts = open_window(app, client, Settings(repository=""))
    tell(client, Status="idle")

    window._button.emit("clicked")

    wizard = Recorder.built[0]
    assert wizard.arguments[:3] == (window, client, settings) and wizard.shown == 1
    assert not window._history.get_sensitive()


def test_a_daemon_that_cannot_be_reached_is_explained(app, client):
    window, _settings, _toasts = open_window(app, client)

    client.answer("read_state", None, "no daemon")

    assert window._page.get_title() == "The backup service is not available"
    assert not window._history.get_sensitive()


def test_a_running_backup_disables_the_button(app, client):
    window, _settings, _toasts = open_window(app, client)

    tell(client, **protected(Status="running"))

    assert window._page.get_title() == "Backing up…" and not window._button.get_sensitive()


def test_a_failed_backup_offers_to_try_again(app, client):
    window, _settings, _toasts = open_window(app, client)

    tell(client, **protected(LastError="disk full"))

    assert window._button.get_label() == "Try again"


def test_without_settings_the_defaults_are_assumed_and_nothing_is_set_up(app, client):
    window, _settings, _toasts = open_window(app, client, with_settings=False)

    tell(client, Status="idle")

    assert window._page.get_title() == "Backups are not set up"
    assert not window.lookup_action("preferences").get_enabled()


# --- what the buttons do -------------------------------------------------------------------------


def test_backing_up_now_starts_the_job_and_refreshes(app, client):
    window, _settings, toasts = open_window(app, client)
    tell(client, **protected())

    window._button.emit("clicked")
    assert not window._button.get_sensitive() and len(client.asked("create_backup")) == 1
    client.answer("create_backup", "job", None)

    assert len(client.asked("read_state")) == 2 and toasts == []


def test_a_backup_that_could_not_start_is_said_in_a_toast(app, client):
    window, _settings, toasts = open_window(app, client)
    tell(client, **protected())
    window._button.emit("clicked")

    client.answer("create_backup", None, "another job is already running")

    assert len(toasts) == 1


def test_unlocking_asks_first_and_only_a_yes_goes_ahead(app, client, dialogs):
    window, _settings, _toasts = open_window(app, client)
    tell(client, **protected(LastError="Failed to create/acquire the lock /r/lock.exclusive"))
    assert window._button.get_label() == "Unlock…"

    window._button.emit("clicked")
    dialogs.respond("cancel")
    assert client.asked("unlock_repository") == []

    window._button.emit("clicked")
    dialogs.respond("unlock")
    assert len(client.asked("unlock_repository")) == 1 and not window._button.get_sensitive()


def test_the_history_button_opens_the_history_window(app, client, monkeypatch):
    monkeypatch.setattr(window_module, "HistoryWindow", Recorder)
    window, _settings, _toasts = open_window(app, client)

    window._history.emit("clicked")

    assert Recorder.built[0].arguments == (window, client) and Recorder.built[0].shown == 1


def test_the_preferences_open_from_their_action(app, client, monkeypatch):
    monkeypatch.setattr(window_module, "PreferencesDialog", Recorder)
    window, settings, _toasts = open_window(app, client)

    window.activate_action("win.preferences", None)

    assert Recorder.built[0].arguments[0] is settings and Recorder.built[0].shown == 1


def test_the_about_dialog_opens_over_the_window_from_its_action(app, client, monkeypatch):
    shown = []
    monkeypatch.setattr(
        window_module, "build_about", lambda: SimpleNamespace(present=lambda parent: shown.append(parent))
    )
    window, _settings, _toasts = open_window(app, client)

    window.activate_action("win.about", None)

    assert shown == [window]


def test_without_settings_the_preferences_do_nothing(app, client, monkeypatch):
    monkeypatch.setattr(window_module, "PreferencesDialog", Recorder)
    window, _settings, _toasts = open_window(app, client, with_settings=False)

    window._on_preferences(None, None)

    assert Recorder.built == []


# --- staying up to date --------------------------------------------------------------------------


def test_a_finished_backup_refreshes_and_a_failure_is_said(app, client):
    window, _settings, toasts = open_window(app, client)

    client.subscriptions["on_backup_finished"]("job", True, "")
    client.subscriptions["on_backup_finished"]("job", False, "disk full")

    assert len(client.asked("read_state")) == 3 and len(toasts) == 1


def test_progress_refreshes_the_view_only_until_it_shows_a_running_backup(app, client):
    window, _settings, _toasts = open_window(app, client)

    client.subscriptions["on_progress"]("job", -1.0, "/home/u/a")
    assert len(client.asked("read_state")) == 2

    tell(client, **protected(Status="running"))
    client.subscriptions["on_progress"]("job", -1.0, "/home/u/b")
    assert len(client.asked("read_state")) == 2


def test_the_view_is_refreshed_on_a_timer_and_when_the_settings_change(app, client):
    window, settings, _toasts = open_window(app, client)

    assert window._on_tick() is GLib.SOURCE_CONTINUE
    settings.callbacks[0][1](settings, "schedule")

    assert len(client.asked("read_state")) == 3


def test_closing_stops_the_timer_and_the_subscriptions(app, client):
    window, _settings, _toasts = open_window(app, client)

    assert window._on_close(window) is False

    assert len(client.unsubscribed) == 2


# --- the application -----------------------------------------------------------------------------


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
        (model.get_item_attribute_value(i, "label").get_string(), model.get_item_attribute_value(i, "action").get_string())
        for i in range(model.get_n_items())
    ]

    assert entries == [("Preferences", "win.preferences"), ("Help", "app.help"), ("About Delta", "win.about")]


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
        SimpleNamespace(BusType=SimpleNamespace(SESSION=0), bus_get_sync=lambda bus, cancellable: connections.append(1) or object()),
    )

    first = app_with_bus._client_for_session()

    assert app_with_bus._client_for_session() is first and connections == [1]


def test_main_sets_up_translations_and_runs_the_application(monkeypatch):
    steps = []
    monkeypatch.setattr(application_module.i18n, "setup", lambda: steps.append("i18n"))
    monkeypatch.setattr(application_module, "DeltaApplication", lambda: SimpleNamespace(run=lambda argv: 5))

    assert main() == 5 and steps == ["i18n"]
