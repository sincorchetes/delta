"""The window asks for the passphrase again when the keyring has lost it, and keeps it only if the repository opens."""

from gi.repository import Adw, Gtk
from status_window_support import open_window, protected, tell
from status_window_support import app, fresh_recorder  # noqa: F401  (fixtures)

MISSING = "The passphrase for this repository is not in the keyring."


def without_passphrase(app, client):
    window, settings, toasts = open_window(app, client)
    tell(client, **protected(LastError=MISSING))
    return window, settings, toasts


def test_a_missing_passphrase_offers_to_enter_it_and_not_to_try_again(app, client):
    window, _settings, _toasts = without_passphrase(app, client)

    assert window._page.get_title() == "The passphrase of your backups is not in the keyring"
    assert window._button.get_label() == "Enter passphrase…" and window._button.get_visible()


def test_the_button_asks_for_the_passphrase_of_the_repository_in_a_dialog(app, client, dialogs):
    window, settings, _toasts = without_passphrase(app, client)

    window._button.emit("clicked")

    dialog, _callback = dialogs.items[-1]
    assert isinstance(dialog, Adw.AlertDialog) and dialog.get_heading() == "Enter the passphrase of your backups"
    assert settings.values["repository-location"] in dialog.get_body()
    assert isinstance(dialog.get_extra_child(), Gtk.PasswordEntry)
    assert dialog.has_response("use") and dialog.get_default_response() == "use" and dialog.get_close_response() == "cancel"


def test_the_passphrase_that_is_typed_goes_to_the_daemon_with_the_repository(app, client, dialogs):
    window, settings, _toasts = without_passphrase(app, client)
    window._button.emit("clicked")
    dialogs.items[-1][0].get_extra_child().set_text("correct horse")

    dialogs.respond("use")

    assert client.asked("use_repository") == [(settings.values["repository-location"], "correct horse")]
    assert not window._button.get_sensitive()


def test_cancelling_asks_nothing_of_the_daemon(app, client, dialogs):
    window, _settings, _toasts = without_passphrase(app, client)
    window._button.emit("clicked")
    dialogs.items[-1][0].get_extra_child().set_text("typed and then cancelled")

    dialogs.respond("cancel")

    assert client.asked("use_repository") == [] and window._button.get_sensitive()


def test_an_empty_passphrase_asks_nothing_of_the_daemon(app, client, dialogs):
    window, _settings, _toasts = without_passphrase(app, client)
    window._button.emit("clicked")

    dialogs.respond("use")

    assert client.asked("use_repository") == []


def test_a_passphrase_that_the_daemon_refuses_is_told_and_the_window_asks_the_state_again(app, client, dialogs):
    window, _settings, toasts = without_passphrase(app, client)
    window._button.emit("clicked")
    dialogs.items[-1][0].get_extra_child().set_text("wrong")
    dialogs.respond("use")
    asked_before = len(client.asked("read_state"))

    client.answer("use_repository", None, "refused")

    assert len(toasts) == 1 and len(client.asked("read_state")) == asked_before + 1
