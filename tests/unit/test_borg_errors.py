"""What borg's stderr is turned into: the text shown and the kind of error raised."""

import json

import pytest

from delta.domain.errors import EngineError, PassphraseError, RepositoryLocked, RepositoryNotFound
from delta.infrastructure.borg_parsing import error_for, log_messages


def log(message="", **fields):
    return json.dumps({"type": "log_message", "message": message, **fields})


# --- flattening --log-json stderr ----------------------------------------------------------------------


def test_each_message_is_one_line_of_the_text():
    assert log_messages(log("first") + "\n" + log("second")) == "first\nsecond"


def test_json_that_is_not_a_log_message_says_nothing():
    stderr = "\n".join([json.dumps({"type": "archive_progress", "message": "ignored"}), "123", log("kept")])

    assert log_messages(stderr) == "kept"


def test_a_log_message_without_text_is_an_empty_line():
    assert log_messages(json.dumps({"type": "log_message"}) + "\nplain") == "\nplain"


def test_a_log_message_is_read_whatever_the_order_of_its_fields():
    assert log_messages(json.dumps({"message": "kept", "type": "log_message"})) == "kept"


def test_a_log_message_holding_another_object_is_read_from_its_own_start():
    assert log_messages(log("kept", extra={"type": "inner"})) == "kept"


# --- which error a failure is --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Repository /x does not exist.", RepositoryNotFound),
        ("/x is not a valid repository. Check repo config.", RepositoryNotFound),
        ("Failed to create/acquire the lock /x/lock.exclusive (timeout).", RepositoryLocked),
        ("passphrase supplied in BORG_PASSPHRASE is incorrect.", PassphraseError),
        ("Wrong passphrase.", PassphraseError),
        ("Enter passphrase for key /x:", EngineError),  # asked for, not refused
        ("wrong number of arguments", EngineError),  # wrong, but not the passphrase
        ("boom", EngineError),
    ],
)
def test_a_failure_is_the_right_kind_of_error_and_keeps_what_borg_said(text, kind):
    error = error_for(2, log(text))

    assert type(error) is kind
    assert str(error) == text


def test_an_engine_error_carries_the_exit_status():
    assert error_for(2, "boom").returncode == 2


def test_a_failure_that_said_nothing_is_described_by_its_exit_status():
    error = error_for(3, "")

    assert (type(error), str(error), error.returncode) == (EngineError, "borg exited with status 3", 3)
