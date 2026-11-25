"""Checking the repository from the status window."""

import pytest
from status_window_support import check_action, open_window, protected, tell
from status_window_support import alerts, app, fresh_recorder  # noqa: F401  (fixtures)


@pytest.mark.parametrize(
    ("properties", "enabled"),
    [
        ({}, True),
        ({"LastError": "disk full"}, True),
        ({"Status": "running"}, False),
        ({"Status": "checking"}, False),
        ({"Status": "browsing"}, False),
        ({"Status": "unavailable", "UnavailableReason": "missing"}, False),
        ({"LastError": "Failed to create/acquire the lock /r/lock.exclusive"}, False),
    ],
)
def test_a_check_is_offered_only_while_nothing_else_is_going_on(app, client, properties, enabled):
    window, _settings, _toasts = open_window(app, client)

    tell(client, **protected(**properties))

    assert check_action(window).get_enabled() is enabled


def test_nothing_can_be_checked_before_the_daemon_has_answered(app, client):
    window, _settings, _toasts = open_window(app, client)

    assert not check_action(window).get_enabled()


def test_a_check_in_progress_shows_it_and_offers_to_cancel(app, client):
    window, _settings, _toasts = open_window(app, client)

    tell(client, **protected(Status="checking"))

    assert window._page.get_title() == "Checking your backups…"
    assert window._button.get_label() == "Cancel" and window._button.get_sensitive()


def test_cancelling_asks_the_daemon_to_stop_and_refreshes_when_it_answers(app, client):
    window, _settings, _toasts = open_window(app, client)
    tell(client, **protected(Status="checking"))

    window._button.emit("clicked")

    assert len(client.asked("cancel_check")) == 1 and not window._button.get_sensitive()
    reads = len(client.asked("read_state"))
    client.answer("cancel_check", None, None)
    assert len(client.asked("read_state")) == reads + 1


def test_a_check_that_goes_well_is_said_in_a_toast(app, client, alerts):
    window, _settings, toasts = open_window(app, client)
    tell(client, **protected())

    check_action(window).activate(None)
    assert len(client.asked("check_repository")) == 1 and not check_action(window).get_enabled()
    client.answer("check_repository", "job-1", None)
    client.subscriptions["on_backup_finished"]("job-1", True, "Your backups were checked and no problems were found.")

    assert [toast.get_title() for toast in toasts] == ["Your backups were checked and no problems were found."]
    assert alerts == []


def test_what_a_check_finds_is_shown_where_it_can_be_read_and_not_twice(app, client, alerts):
    window, _settings, toasts = open_window(app, client)
    tell(client, **protected())
    finding = "The check found problems in your backups. " + "Borg said: x " * 40

    check_action(window).activate(None)
    client.answer("check_repository", "job-1", None)
    client.subscriptions["on_backup_finished"]("job-1", False, finding)

    assert alerts == [("Checking your backups", finding, True)] and toasts == []


def test_a_check_that_could_not_start_is_said_in_a_dialog(app, client, alerts):
    window, _settings, _toasts = open_window(app, client)
    tell(client, **protected())

    check_action(window).activate(None)
    client.answer("check_repository", None, "another job is already running")

    assert alerts == [("Checking your backups", "another job is already running", True)]


def test_a_result_that_arrives_before_the_reply_is_not_lost(app, client, alerts):
    window, _settings, toasts = open_window(app, client)
    tell(client, **protected())

    check_action(window).activate(None)
    client.subscriptions["on_backup_finished"]("job-1", True, "done")
    client.answer("check_repository", "job-1", None)

    assert [toast.get_title() for toast in toasts] == ["done"]


def test_the_failure_of_another_job_is_still_a_toast_when_no_check_runs(app, client, alerts):
    window, _settings, toasts = open_window(app, client)

    client.subscriptions["on_backup_finished"]("job", False, "disk full")

    assert len(toasts) == 1 and alerts == []
