"""Browsing a folder of a backup: rows compared with the real disk, searching, filtering, picking."""

import os

import pytest
from gtk_helpers import labels, of_type
from gi.repository import Adw, Gtk

from delta.ui.folder_browser import FolderBrowser

OLD = 1_700_000_000


@pytest.fixture
def root(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    same = folder / "same.txt"
    same.write_text("hello")
    os.utime(same, (OLD, OLD))
    (folder / "changed.txt").write_text("now it is longer")
    (folder / "sub").mkdir()
    return folder


def backed_up():
    """Folders first, then by name: sub, changed.txt, gone.txt, same.txt."""
    return [
        {"name": "same.txt", "is_dir": False, "size": 5, "mtime": OLD},
        {"name": "changed.txt", "is_dir": False, "size": 3, "mtime": OLD},
        {"name": "gone.txt", "is_dir": False, "size": 9, "mtime": OLD},
        {"name": "sub", "is_dir": True, "size": 0, "mtime": OLD},
    ]


class Harness:
    def __init__(self, client, root):
        self.client, self.root = client, str(root)
        self.files, self.changes, self.restores, self.deleted = [], 0, [], 0
        self.browser = FolderBrowser(
            client,
            lambda path, size: self.files.append((path, size)),
            self._changed,
            lambda paths, in_place: self.restores.append((paths, in_place)),
            lambda: setattr(self, "deleted", self.deleted + 1),
        )

    def _changed(self):
        self.changes += 1

    def names(self):
        return [row.name for row in self.browser._shown]

    def row(self, name):
        return self.browser._list.get_row_at_index(self.names().index(name))

    def visible(self):
        return self.browser._stack.get_visible_child_name()


@pytest.fixture
def harness(client, root):
    seen = Harness(client, root)
    yield seen
    seen.browser.close()


@pytest.fixture
def opened(harness, client):
    harness.browser.open("snap", harness.root)
    client.answer("list_folder", backed_up(), None)
    return harness


# --- listing ---------------------------------------------------------------------------------------


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


# --- moving around ---------------------------------------------------------------------------------


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


# --- restoring from a row --------------------------------------------------------------------------


def restore_button(row):
    return next(b for b in of_type(row, Gtk.Button) if b.get_icon_name() == "document-revert-symbolic")


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


# --- picking several -------------------------------------------------------------------------------


def test_selection_mode_ticks_items_and_lists_what_is_ticked(opened):
    opened.browser._select.set_active(True)
    assert opened.browser.selecting

    opened.browser._checks["gone.txt"].set_active(True)
    opened.browser._checks["changed.txt"].set_active(True)

    assert opened.browser.selected_paths() == [opened.root + "/changed.txt", opened.root + "/gone.txt"]
    assert opened.browser.selected_items() == [
        (opened.root + "/changed.txt", False),
        (opened.root + "/gone.txt", True),
    ]


def test_an_item_that_is_the_same_as_today_cannot_be_ticked(opened):
    opened.browser._select.set_active(True)

    check = opened.browser._checks["same.txt"]

    assert not check.get_sensitive() and not check.get_active()


def test_clicking_a_row_in_selection_mode_ticks_it_instead_of_opening_it(opened):
    opened.browser._select.set_active(True)

    opened.browser._list.emit("row-activated", opened.row("gone.txt"))
    assert opened.browser._checks["gone.txt"].get_active() and opened.files == []

    opened.browser._list.emit("row-activated", opened.row("gone.txt"))
    assert not opened.browser._checks["gone.txt"].get_active()


def test_a_row_without_a_tick_box_in_selection_mode_does_nothing(opened):
    opened.browser._select.set_active(True)
    opened.browser._checks.pop("gone.txt")

    opened.browser._list.emit("row-activated", opened.row("gone.txt"))

    assert opened.files == []


def test_escape_clears_the_search_then_leaves_selection_then_does_nothing(opened):
    opened.browser._select.set_active(True)
    opened.browser._search.set_text("txt")

    assert opened.browser.escape() is True and opened.browser._search.get_text() == ""
    assert opened.browser.escape() is True and not opened.browser.selecting
    assert opened.browser.escape() is False


# --- searching and filtering -----------------------------------------------------------------------


def test_typing_waits_for_a_pause_and_then_searches_the_folder(opened, client):
    opened.browser._search.set_text("txt")

    opened.browser._on_query(opened.browser._search)
    assert opened.browser._timer and client.asked("search_folder") == []
    opened.browser._search_now()

    assert client.asked("search_folder") == [("snap", opened.root, "txt")] and opened.visible() == "loading"
    client.answer("search_folder", [{"name": "sub/deep.txt", "is_dir": False, "size": 1, "mtime": OLD}], None)
    assert opened.names() == ["sub/deep.txt"]


def test_a_search_with_no_match_says_nothing_was_found(opened, client):
    opened.browser._search.set_text("zzz")
    opened.browser._search_now()

    client.answer("search_folder", [], None)

    assert opened.browser._message.get_title() == "Nothing found"


def test_clearing_the_search_brings_the_folder_back(opened):
    opened.browser._search.set_text("txt")
    opened.browser._on_query(opened.browser._search)
    opened.browser._search.set_text("")

    opened.browser._on_query(opened.browser._search)

    assert opened.browser._timer == 0 and opened.visible() == "list" and len(opened.names()) == 4


def test_a_search_that_hit_the_limit_says_so_under_the_results(opened, client):
    opened.browser._search.set_text("n")
    opened.browser._search_now()
    hits = [{"name": f"n{i}", "is_dir": False, "size": 1, "mtime": OLD} for i in range(1000)]

    client.answer("search_folder", hits, None)

    assert any("1000" in (row.get_title() or "") for row in of_type(opened.browser._list, Adw.ActionRow))


def test_the_changed_filter_shows_what_was_deleted_or_modified_and_the_deleted_filter_only_the_former(opened, client):
    opened.browser._filter.set_selected(1)
    assert opened.visible() == "loading" or opened.names()  # waiting for the comparison, or already drawn
    client.answer(
        "list_changed",
        [
            {"name": "gone.txt", "is_dir": False, "size": 9, "mtime": OLD},
            {"name": "changed.txt", "is_dir": False, "size": 3, "mtime": OLD},
            {"name": "same.txt", "is_dir": False, "size": 5, "mtime": OLD},
        ],
        None,
    )
    assert "same.txt" not in opened.names() and {"gone.txt", "changed.txt"} <= set(opened.names())

    opened.browser._filter.set_selected(2)
    assert "changed.txt" not in opened.names() and "gone.txt" in opened.names()


def test_a_filter_with_nothing_to_show_says_so(opened, client):
    opened.browser._filter.set_selected(2)

    client.answer("list_changed", [], None)

    assert opened.browser._message.get_title() == "Nothing to show"


def test_going_into_a_folder_resets_the_controls(opened):
    opened.browser._search.set_text("txt")
    opened.browser._filter.set_selected(1)
    opened.browser._select.set_active(True)

    opened.browser._navigate(opened.root + "/sub")

    assert opened.browser._search.get_text() == "" and opened.browser._filter.get_selected() == 0
    assert not opened.browser.selecting


def test_the_marks_and_the_comparison_can_be_refreshed(opened, client):
    opened.browser.refresh_marks()
    opened.browser.refresh_all()

    assert len(client.asked("list_changed")) == 2


def test_the_search_box_can_be_focused_and_the_browser_closed(opened):
    opened.browser.focus_search()
    opened.browser._search.set_text("a")
    opened.browser._on_query(opened.browser._search)

    opened.browser.close()

    assert opened.browser._timer == 0
