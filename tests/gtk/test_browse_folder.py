"""«Browse as a folder»: hidden where backups cannot be mounted, and one job at a time where they can."""

import pytest

from delta.ui.browse_folder import BrowseFolder
from delta.ui.job_tracker import JobTracker
from delta.ui.version_preview import Target

FOLDER = "/run/user/1000/delta/browse/snapshot"
TARGET = Target("snap1", "/home/ana/docs/a.txt", 5)


@pytest.fixture
def world(client):
    tracker, toasts, changes, shown = JobTracker(), [], [], []
    browse = BrowseFolder(client, tracker, toasts.append, lambda: changes.append(1), shown.append)
    client.answer("read_state", {"CanMount": True}, None)
    browse.sync(TARGET)
    return browse, tracker, toasts, shown, changes


def open_it(browse, client, tracker):
    browse.button.emit("clicked")
    client.answer("mount_snapshot", "job1", None)
    tracker.on_finished("job1", True, FOLDER)


def test_the_button_is_hidden_until_the_daemon_says_it_can_mount(client):
    browse = BrowseFolder(client, JobTracker(), print, lambda: None, print)
    assert not browse.button.get_visible()

    client.answer("read_state", {"CanMount": True}, None)
    assert browse.button.get_visible()


@pytest.mark.parametrize("answer", [({"CanMount": False}, None), ({}, None), (None, "no daemon")])
def test_it_stays_hidden_without_mounting_or_without_a_daemon(client, answer):
    browse = BrowseFolder(client, JobTracker(), print, lambda: None, print)

    client.answer("read_state", *answer)

    assert not browse.button.get_visible()


def test_with_nothing_chosen_there_is_nothing_to_open(world):
    browse, _tracker, _toasts, _shown, _changes = world

    browse.sync(None)

    assert not browse.button.get_sensitive()
    browse.button.emit("clicked")
    assert browse._state == "closed"


def test_opening_asks_for_the_chosen_backup_and_shows_the_item_in_files(world, client):
    browse, tracker, _toasts, shown, _changes = world

    browse.button.emit("clicked")
    assert client.asked("mount_snapshot") == [("snap1",)] and browse._state == "opening"
    browse.sync(TARGET)
    assert browse.button.get_label() == "Preparing the backup…" and not browse.button.get_sensitive()

    client.answer("mount_snapshot", "job1", None)
    tracker.on_finished("job1", True, FOLDER)

    assert shown == [FOLDER + "/home/ana/docs/a.txt"]
    browse.sync(TARGET)
    assert browse.button.get_label() == "Close the folder" and browse.button.get_sensitive()


def test_a_second_click_while_busy_does_nothing(world, client):
    browse, _tracker, _toasts, _shown, _changes = world
    browse.button.emit("clicked")

    browse.button.emit("clicked")

    assert len(client.asked("mount_snapshot")) == 1


def test_an_opening_that_fails_says_why_and_goes_back_to_closed(world, client):
    browse, tracker, toasts, shown, _changes = world

    browse.button.emit("clicked")
    client.answer("mount_snapshot", "job1", None)
    tracker.on_finished("job1", False, "the repository is locked")

    assert toasts and shown == [] and browse._state == "closed" and not browse._opened


def test_closing_asks_the_daemon_and_the_button_offers_to_open_again(world, client):
    browse, tracker, toasts, _shown, _changes = world
    open_it(browse, client, tracker)

    browse.button.emit("clicked")
    assert browse._state == "closing"
    browse.sync(TARGET)
    assert browse.button.get_label() == "Closing…"
    client.answer("unmount_snapshot", "job2", None)
    tracker.on_finished("job2", True, "")

    assert browse._state == "closed" and not browse._opened and toasts == []
    browse.sync(TARGET)
    assert browse.button.get_label() == "Browse as a folder"


def test_when_the_daemon_closes_it_the_window_is_told_and_can_open_again(world, client):
    browse, tracker, toasts, _shown, changes = world
    open_it(browse, client, tracker)
    changes.clear()

    client.subscriptions["on_snapshot_closed"]("sleep-or-lock")

    assert not browse._opened and browse._state == "closed" and changes and toasts == ["The backup folder was closed."]


def test_a_closing_signal_without_a_folder_open_says_nothing(world, client):
    _browse, _tracker, toasts, _shown, _changes = world

    client.subscriptions["on_snapshot_closed"]("sleep-or-lock")

    assert toasts == []


def test_the_signal_that_answers_our_own_closing_is_not_news(world, client):
    browse, tracker, toasts, _shown, _changes = world
    open_it(browse, client, tracker)
    browse.button.emit("clicked")

    client.subscriptions["on_snapshot_closed"]("requested")

    assert toasts == [] and browse._state == "closing"


def test_closing_the_window_closes_an_open_folder_and_lets_go_of_the_signal(world, client):
    browse, tracker, _toasts, _shown, _changes = world
    open_it(browse, client, tracker)

    browse.close()

    assert client.unsubscribed == [1] and len(client.asked("unmount_snapshot")) == 1
    client.answer("unmount_snapshot", None, None)  # nobody waits for it


def test_closing_the_window_with_nothing_open_asks_for_nothing(world, client):
    browse, _tracker, _toasts, _shown, _changes = world

    browse.close()

    assert client.asked("unmount_snapshot") == []
