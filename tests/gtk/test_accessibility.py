"""What a screen reader is told: names for icon-only controls, nothing for decoration."""

import base64

import pytest
from gtk_helpers import of_type
from gi.repository import Gtk

from delta.ui.a11y import decorative_icon, loading_spinner, named, tipped
from delta.ui.folder_listing import Change, FolderRow
from delta.ui.folder_row import build_row
from delta.ui.path_list import PathListGroup
from delta.ui.preview_pane import PreviewPane
from delta.ui.wizard import PathState, WizardModel
from delta.ui.wizard_base import flat_icon_button
from delta.ui.wizard_pages import FoldersPage


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def has_name(widget):
    return Gtk.test_accessible_has_property(widget, Gtk.AccessibleProperty.LABEL)


def entry(change=Change.MODIFIED, is_dir=False, name="photo.jpg"):
    return FolderRow(name=name, is_dir=is_dir, size=10, mtime=1, detail="10 bytes", change=change)


# --- the helpers ---------------------------------------------------------------------------------


def test_a_control_can_be_given_a_name_and_is_handed_back():
    button = Gtk.Button(icon_name="go-previous-symbolic")
    assert not has_name(button)

    assert named(button, "Back") is button and has_name(button)


def test_an_icon_only_control_gets_the_same_text_as_tooltip_and_name():
    button = tipped(Gtk.Button(icon_name="go-previous-symbolic"), "Back")

    assert button.get_tooltip_text() == "Back" and has_name(button)


def test_a_decorative_icon_is_hidden_from_screen_readers():
    assert decorative_icon("folder-symbolic").get_accessible_role() == Gtk.AccessibleRole.PRESENTATION


def test_a_loading_indicator_says_it_is_loading():
    spinner = loading_spinner()

    assert spinner.get_spinning() and has_name(spinner)


# --- the folder browser's rows -------------------------------------------------------------------


def revert(row):
    return next(b for b in of_type(row, Gtk.Button) if b.get_icon_name() == "document-revert-symbolic")


def test_every_row_has_a_restore_button_that_says_which_item_it_restores():
    row, _check = build_row(entry(name="a.jpg"), False, False, lambda on: None, lambda: None)
    other, _check = build_row(entry(name="b.jpg"), False, False, lambda on: None, lambda: None)

    assert has_name(revert(row)) and has_name(revert(other))


def test_the_tick_of_a_row_says_which_item_it_selects():
    _row, check = build_row(entry(), True, False, lambda on: None, lambda: None)

    assert has_name(check)


def test_the_icons_of_a_row_are_decoration():
    row, _check = build_row(entry(is_dir=True), False, False, lambda on: None, lambda: None)

    icons = [i for i in of_type(row, Gtk.Image) if i.get_icon_name() in ("folder-symbolic", "go-next-symbolic")]
    assert len(icons) == 2
    assert all(i.get_accessible_role() == Gtk.AccessibleRole.PRESENTATION for i in icons)


@pytest.mark.parametrize("change", [Change.UNCHANGED, Change.MODIFIED, Change.DELETED])
def test_the_tag_that_says_how_a_row_differs_is_never_dimmed(change):
    row, _check = build_row(entry(change), False, False, lambda on: None, lambda: None)

    assert not any(label.has_css_class("dim-label") for label in of_type(row, Gtk.Label))


# --- buttons that carry only an icon --------------------------------------------------------------


def test_the_wizards_remove_button_has_a_name():
    assert has_name(flat_icon_button("list-remove-symbolic", "Remove"))


def test_each_remove_button_of_a_list_of_folders_says_which_folder():
    group = PathListGroup(None, "Folders", "Which", "Nothing", lambda paths: None, lambda problem: None)
    group.set_paths(("/home/u/docs", "/home/u/music"))

    assert all(has_name(of_type(row, Gtk.Button)[0]) for row in group._rows)


def test_each_remove_button_of_the_wizards_folders_says_which_folder():
    chosen = WizardModel(home="/home/u", inspect=lambda path: PathState.MISSING, folders=("/home/u/docs",))
    page = FoldersPage(chosen, None, lambda: None)

    assert has_name(of_type(page._list, Gtk.Button)[0])


# --- the preview ---------------------------------------------------------------------------------


@pytest.fixture
def picture(tmp_path):
    path = tmp_path / "sunset.png"
    path.write_bytes(PNG)
    return path


def test_the_loading_page_of_the_preview_has_a_name():
    pane = PreviewPane()

    assert has_name(pane.get_child_by_name("loading"))


def test_a_previewed_image_is_described_by_its_file_name(picture):
    pane = PreviewPane()

    assert pane.show_image(str(picture)) is True
    assert pane._picture.get_alternative_text() == "Preview of sunset.png"
