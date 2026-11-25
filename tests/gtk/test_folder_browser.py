"""Browsing a folder of a backup: rows compared with the real disk, opening and restoring."""

from gtk_helpers import labels
from folder_browser_support import OLD, restore_button
from folder_browser_support import harness, opened, root  # noqa: F401  (fixtures)


def test_opening_asks_for_the_folder_and_shows_a_spinner_meanwhile(harness, client):
    harness.browser.open("snap", harness.root)

    assert client.asked("list_folder") == [("snap", harness.root)]
    assert harness.visible() == "loading" and harness.browser.folder == harness.root
    assert not harness.browser.can_go_up


def test_the_listing_arrives_compared_with_the_disk(opened):
    assert opened.visible() == "list"
    assert opened.names() == ["sub", "changed.txt", "gone.txt", "same.txt"]
    shown = labels(opened.browser._list)
    assert "Deleted" in shown and "Modified" in shown and "Unchanged" in shown


def test_nothing_is_drawn_while_the_folder_is_still_on_its_way(harness, client):
    harness.browser.open("snap", harness.root)

    harness.browser.refresh_marks()

    assert harness.visible() == "loading" and harness.names() == []


def test_after_the_folder_arrives_the_comparison_below_it_is_asked_for(opened, client):
    assert client.asked("list_changed") == [("snap", opened.root)]


def test_an_empty_folder_says_it_was_empty(harness, client):
    harness.browser.open("snap", harness.root)

    client.answer("list_folder", [], None)

    assert harness.visible() == "message" and harness.browser._message.get_title() == "This folder was empty"


def test_a_folder_that_cannot_be_read_is_explained(harness, client):
    harness.browser.open("snap", harness.root)

    client.answer("list_folder", None, "the repository is locked")

    assert harness.visible() == "message" and harness.browser._message.get_title() == "Could not read this folder"


def test_folders_that_changed_inside_are_marked_once_the_comparison_arrives(opened, client):
    client.answer("list_changed", [{"name": "sub/new.txt", "is_dir": False, "size": 1, "mtime": OLD}], None)

    assert "Changed inside" in labels(opened.browser._list)


def test_a_comparison_that_fails_is_not_worth_an_error_page_unless_a_filter_needs_it(opened, client):
    client.answer("list_changed", None, "boom")
    assert opened.visible() == "list"

    opened.browser._filter.set_selected(1)
    client.answer("list_changed", None, "boom")
    assert opened.visible() == "message"


def test_opening_a_folder_goes_into_it_and_up_comes_back(opened, client):
    opened.browser._list.emit("row-activated", opened.row("sub"))

    assert client.asked("list_folder")[-1] == ("snap", opened.root + "/sub") and opened.browser.can_go_up
    opened.browser.go_up()
    assert client.asked("list_folder")[-1] == ("snap", opened.root) and not opened.browser.can_go_up
    opened.browser.go_up()
    assert len(client.asked("list_folder")) == 3  # already at the top: nowhere to go


def test_opening_a_file_reports_it_with_its_size(opened):
    opened.browser._list.emit("row-activated", opened.row("same.txt"))

    assert opened.files == [(opened.root + "/same.txt", 5)]


def test_a_row_outside_the_opened_folder_is_never_followed(opened):
    opened.browser._data.root = opened.root + "/elsewhere"

    opened.browser._list.emit("row-activated", opened.row("sub"))

    assert opened.files == [] and len(opened.client.asked("list_folder")) == 1


def test_a_row_the_listing_does_not_have_is_ignored(opened):
    row = opened.row("sub")
    opened.browser._shown = []

    opened.browser._list.emit("row-activated", row)

    assert opened.files == [] and len(opened.client.asked("list_folder")) == 1


def test_a_deleted_item_goes_back_in_place_and_a_changed_one_as_a_copy(opened):
    restore_button(opened.row("gone.txt")).emit("clicked")
    restore_button(opened.row("changed.txt")).emit("clicked")

    assert opened.restores == [([opened.root + "/gone.txt"], True), ([opened.root + "/changed.txt"], False)]


def test_restore_deleted_is_a_button_that_can_be_frozen_while_a_job_runs(opened):
    opened.browser._deleted.emit("clicked")
    assert opened.deleted == 1

    opened.browser.set_busy(True)
    assert not opened.browser._deleted.get_sensitive()
    opened.browser.set_busy(False)
    assert opened.browser._deleted.get_sensitive()


def test_what_was_restored_says_so_until_the_user_moves_on(opened):
    opened.browser.mark_restored([opened.root + "/changed.txt", "/elsewhere/other.txt"])

    assert "Restored" in labels(opened.browser._list)
    opened.browser._list.emit("row-activated", opened.row("sub"))
    assert opened.browser._restored == set()
