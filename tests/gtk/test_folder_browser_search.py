"""Browsing a folder of a backup: selecting, searching and filtering."""

from gtk_helpers import of_type
from gi.repository import Adw
from folder_browser_support import OLD
from folder_browser_support import harness, opened, root  # noqa: F401  (fixtures)


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
