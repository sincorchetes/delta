"""The row of action buttons: side by side while they fit, in lines when they do not, never in the keyboard's way."""

import pytest
from gi.repository import Gtk

from delta.ui.button_row import GAP, button_row

LONG = ("Replace the current version…", "Open", "Browse as a folder", "Restore as a copy")

# GTK 4.16.7 (Rocky and AlmaLinux 10) measures this FlowBox as one button wide, not as all of them side by side (both the
# minimum and the natural width are the widest button), so these two checks cannot tell whether the row wraps there. From
# GTK 4.18 on they hold.
measures_the_row_as_one_button = pytest.mark.skipif(
    (Gtk.get_major_version(), Gtk.get_minor_version()) < (4, 18),
    reason="before GTK 4.18 a FlowBox is measured as wide as its widest child",
)


def buttons(*labels):
    return [Gtk.Button(label=label) for label in labels]


def slot(row, index):
    return row.get_child_at_index(index)


def test_the_buttons_are_in_the_row_in_the_order_given():
    items = buttons("One", "Two", "Three")

    row = button_row(items)

    assert [slot(row, index).get_child() for index in range(3)] == items
    assert slot(row, 3) is None


@measures_the_row_as_one_button
def test_a_row_can_be_narrower_than_all_its_buttons_side_by_side():
    row = button_row(buttons(*LONG))

    minimum, natural, _, _ = row.measure(Gtk.Orientation.HORIZONTAL, -1)

    assert minimum < natural  # a window does not have to be as wide as the whole row


@measures_the_row_as_one_button
def test_when_the_width_is_short_the_buttons_go_to_another_line():
    row = button_row(buttons(*LONG))
    minimum, natural, _, _ = row.measure(Gtk.Orientation.HORIZONTAL, -1)

    one_line = row.measure(Gtk.Orientation.VERTICAL, natural)[1]
    several_lines = row.measure(Gtk.Orientation.VERTICAL, minimum)[0]

    assert several_lines > one_line


def test_the_row_keeps_a_margin_on_every_side_and_a_gap_between_buttons():
    row = button_row(buttons("One", "Two"))

    assert (row.get_margin_start(), row.get_margin_end(), row.get_margin_top(), row.get_margin_bottom()) == (GAP,) * 4
    assert row.get_column_spacing() == row.get_row_spacing() == GAP


def test_the_keyboard_stops_at_each_button_and_not_at_its_slot():
    items = buttons("One", "Two")

    row = button_row(items)

    assert not slot(row, 0).get_focusable() and not slot(row, 1).get_focusable()
    assert all(button.get_focusable() for button in items)


def test_nothing_in_the_row_can_be_selected():
    assert button_row(buttons("One")).get_selection_mode() == Gtk.SelectionMode.NONE


def test_a_hidden_button_takes_no_room_and_comes_back_with_its_button():
    items = buttons("One", "Two")
    items[1].set_visible(False)

    row = button_row(items)
    assert slot(row, 0).get_visible() and not slot(row, 1).get_visible()

    items[1].set_visible(True)
    assert slot(row, 1).get_visible()
