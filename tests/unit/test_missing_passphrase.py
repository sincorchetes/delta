"""A passphrase that the keyring no longer has is told by the window, which asks for it again."""

from datetime import datetime

import pytest

from delta.domain import errors
from delta.domain.errors import PassphraseError, is_missing_passphrase_message, missing_passphrase
from delta.infrastructure.borg_runner import BorgRunner
from delta.ui.status import Action, DaemonSnapshot, Health, build_status

ENGLISH = "The passphrase for this repository is not in the keyring."
NOW = datetime(2026, 11, 10, 15, 0, 0)


def test_the_message_of_the_engine_is_the_one_that_is_recognised():
    assert missing_passphrase() == ENGLISH
    assert is_missing_passphrase_message(missing_passphrase())


def test_a_daemon_in_another_language_is_recognised_by_its_original_wording(monkeypatch):
    monkeypatch.setattr(errors, "_", lambda text: "La contraseña de este repositorio no está en el llavero.")

    assert is_missing_passphrase_message(ENGLISH)


def test_the_window_in_another_language_recognises_what_the_daemon_said_in_it(monkeypatch):
    monkeypatch.setattr(errors, "_", lambda text: "La contraseña de este repositorio no está en el llavero.")

    assert is_missing_passphrase_message("La contraseña de este repositorio no está en el llavero.")


@pytest.mark.parametrize("text", ["", "disk full", "The passphrase is incorrect.", "keyring"])
def test_other_messages_are_not_a_missing_passphrase(text):
    assert not is_missing_passphrase_message(text)


def test_a_backup_without_the_passphrase_in_the_keyring_fails_with_that_message(tmp_path):
    class Keyring:
        def get(self, key):
            return None

    runner = BorgRunner(env={"BORG_BASE_DIR": str(tmp_path)}, secrets=Keyring())

    with pytest.raises(PassphraseError) as raised:
        runner._pass_passphrase(None, type("Repo", (), {"location": "/r"})())

    assert is_missing_passphrase_message(str(raised.value))


def view(**fields):
    return build_status(DaemonSnapshot(repository="/backups/repo", **fields), NOW)


def test_a_missing_passphrase_offers_to_type_it_instead_of_trying_again():
    shown = view(last_error=ENGLISH, last_backup=1)

    assert shown.health is Health.NO_PASSPHRASE
    assert shown.action is Action.ENTER_PASSPHRASE and shown.action_label == "Enter passphrase…"
    assert shown.action_enabled and not shown.can_back_up_now
    assert "passphrase" in shown.title and "keyring" in shown.title


def test_a_running_backup_still_wins_over_a_missing_passphrase():
    assert view(status="running", last_error=ENGLISH).health is Health.RUNNING


def test_a_missing_drive_still_wins_over_a_missing_passphrase():
    assert view(status="unavailable", last_error=ENGLISH, reason="missing").health is Health.UNAVAILABLE


def test_the_state_uses_a_shipped_icon():
    assert view(last_error=ENGLISH).icon_name == "dialog-password-symbolic"
