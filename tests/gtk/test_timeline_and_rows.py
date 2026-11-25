"""Shortcuts, the timeline and folder rows, as real widgets."""

from gtk_helpers import labels, of_type
from gi.repository import Gtk
from delta.ui import shortcuts
from delta.ui.folder_listing import Change, change_label
from delta.ui.folder_row import build_row, cap_notice_row
from delta.ui.timeline import Timeline
from small_widgets_support import entry, restore_button
from small_widgets_support import chosen, line, opened  # noqa: F401  (fixtures)


def test_each_shortcut_runs_its_action_and_says_whether_the_key_was_used():
    box = Gtk.Box()
    ran = []
    shortcuts.install(
        box,
        {
            "search": lambda: ran.append("search") or True,
            "back": lambda: ran.append("back") or False,  # not used: the key carries on
            "older": lambda: ran.append("older"),  # no answer counts as used
        },
    )
    controller = next(c for c in (box.observe_controllers().get_item(i) for i in range(2)) if c is not None)

    results = [
        controller.get_item(i).get_action().activate(Gtk.ShortcutActionFlags.EXCLUSIVE, box, None)
        for i in range(controller.get_n_items())
    ]

    assert ran == ["search", "back", "older"]
    assert results == [True, False, True]


def test_the_first_version_is_chosen_when_the_list_is_filled(line, chosen):
    assert line.selected.snapshot == "s3"
    assert [v.snapshot for v in chosen] == ["s3"]


def test_stepping_goes_to_the_next_older_or_newer_version(line, chosen):
    line.step(1)
    line.step(1)
    line.step(-1)

    assert [v.snapshot for v in chosen] == ["s3", "s2", "s1", "s2"]


def test_stepping_past_either_end_stays_put(line, chosen):
    line.step(-1)
    for _ in range(5):
        line.step(1)

    assert line.selected.snapshot == "s1"
    assert [v.snapshot for v in chosen] == ["s3", "s2", "s1"]


def test_the_same_row_being_selected_again_is_not_a_new_choice(line, chosen):
    row = line._list.get_selected_row()

    line._on_row_selected(line._list, row)

    assert len(chosen) == 1


def test_opening_a_version_is_reported(line, opened):
    line._list.emit("row-activated", line._list.get_selected_row())

    assert opened == [True]


def test_with_nothing_filled_nothing_is_selected_and_stepping_does_nothing():
    empty = Timeline(lambda v: None, lambda: None)

    empty.step(1)

    assert empty.selected is None


def test_a_row_offers_to_restore_and_says_how_it_differs(monkeypatch):
    restored = []
    row, check = build_row(entry(Change.MODIFIED), False, False, lambda on: None, lambda: restored.append(1))

    restore_button(row).emit("clicked")

    assert check is None and restored == [1]
    assert change_label(Change.MODIFIED) in labels(row)
    assert restore_button(row).get_tooltip_text() == "Restore as a copy"


def test_a_deleted_item_is_put_back_not_copied():
    row, _check = build_row(entry(Change.DELETED), False, False, lambda on: None, lambda: None)

    assert restore_button(row).get_tooltip_text() == "Put it back"


def test_what_is_the_same_as_today_cannot_be_restored_or_ticked():
    row, check = build_row(entry(Change.UNCHANGED), True, True, lambda on: None, lambda: None)

    assert not restore_button(row).get_sensitive()
    assert "nothing to restore" in restore_button(row).get_tooltip_text()
    assert not check.get_active() and not check.get_sensitive()


def test_a_row_in_selection_mode_reports_ticks():
    ticks = []
    _row, check = build_row(entry(), True, False, ticks.append, lambda: None)

    check.set_active(True)

    assert ticks == [True]


def test_a_restored_row_says_so_whatever_it_was():
    row, _check = build_row(entry(Change.DELETED), False, False, lambda on: None, lambda: None, restored=True)

    assert "Restored" in labels(row)


def test_a_folder_row_shows_an_arrow_to_go_in():
    row, _check = build_row(
        entry(Change.UNKNOWN, is_dir=True, name="Pictures"), False, False, lambda on: None, lambda: None
    )

    assert "go-next-symbolic" in [image.get_icon_name() for image in of_type(row, Gtk.Image)]


def test_a_search_that_hit_the_limit_says_how_many_are_shown():
    assert "1000" in cap_notice_row(1000).get_title()
