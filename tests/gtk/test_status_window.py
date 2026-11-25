"""The status window, driven through a stand-in daemon client."""

from types import SimpleNamespace
from gi.repository import GLib
from delta.ui import window as window_module
from status_window_support import Recorder, Settings, open_window, protected, tell
from status_window_support import app, fresh_recorder  # noqa: F401  (fixtures)


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
