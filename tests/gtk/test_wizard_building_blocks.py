"""The choosers, the destination page and the list of paths: the wizard's building blocks, as real widgets."""

import pytest
from gtk_helpers import of_type
from gi.repository import Adw, Gio, GLib, Gtk
from delta.ui import path_list, wizard_destination
from delta.ui.path_list import PathListGroup
from delta.ui.wizard import WizardModel
from delta.ui.wizard_base import Page, choose_file, choose_folder, flat_icon_button
from small_widgets_support import Drive, destination_page
from small_widgets_support import file_dialog, paths  # noqa: F401  (fixtures)


@pytest.mark.parametrize("choose", [choose_folder, choose_file])
def test_a_chosen_path_is_handed_over(file_dialog, choose):
    chosen = []
    choose(None, "Pick", chosen.append)

    file_dialog.last.callback(file_dialog.last, Gio.File.new_for_path("/home/u/Pictures"))

    assert chosen == ["/home/u/Pictures"] and file_dialog.last.title == "Pick"


def test_the_chooser_opens_where_it_is_told_to_and_nowhere_in_particular_otherwise(file_dialog):
    choose_folder(None, "Pick", lambda path: None, "/media/disk")
    assert file_dialog.last.initial == "/media/disk"

    choose_folder(None, "Pick", lambda path: None)
    assert file_dialog.last.initial is None


@pytest.mark.parametrize("choose", [choose_folder, choose_file])
def test_a_dismissed_or_pathless_choice_is_ignored(file_dialog, choose):
    chosen = []
    choose(None, "Pick", chosen.append)

    file_dialog.last.callback(file_dialog.last, GLib.Error("dismissed", domain="test", code=1))
    file_dialog.last.callback(file_dialog.last, Gio.File.new_for_uri("https://example.org/x"))

    assert chosen == []


def test_a_flat_icon_button_has_its_icon_and_tooltip():
    button = flat_icon_button("list-remove-symbolic", "Remove")

    assert button.has_css_class("flat") and button.get_tooltip_text() == "Remove"


def test_a_page_shows_and_hides_its_problems():
    page = Page(WizardModel(home="/home/u", inspect=lambda path: None), None, lambda: None)
    page._finish_layout()

    page.show_problems(["First", "Second"])
    assert page._problems.get_visible() and page._problems.get_text() == "First\nSecond"

    page.show_problems([])
    assert not page._problems.get_visible()


def test_without_connected_drives_only_the_folder_is_offered(monkeypatch):
    page, _model, _changes = destination_page(monkeypatch)

    assert "Connected drives" not in [group.get_title() for group in of_type(page, Adw.PreferencesGroup)]


def test_connected_drives_are_listed_and_a_drive_fills_in_its_folder(monkeypatch):
    page, model, changes = destination_page(monkeypatch, [Drive()])

    assert "Connected drives" in [group.get_title() for group in of_type(page, Adw.PreferencesGroup)]
    page._on_use_drive(None, Drive())

    assert model.destination == "/run/media/u/disk/delta-backups" and changes[-1] == model.destination


def test_typing_a_folder_updates_the_model(monkeypatch):
    page, model, changes = destination_page(monkeypatch)

    page._path.set_text("~/Backups")

    assert model.destination == "~/Backups" and changes == ["~/Backups"]


def test_choosing_a_folder_fills_in_the_path(monkeypatch):
    page, model, _changes = destination_page(monkeypatch)
    asked = []
    monkeypatch.setattr(
        wizard_destination,
        "choose_folder",
        lambda window, title, on_chosen, start: (asked.append(start), on_chosen("/media/disk")),
    )
    model.destination = "~/Backups/new"
    start = model.chooser_start()

    page._on_choose(None)

    assert model.destination == "/media/disk" and asked == [start]


def test_an_empty_list_says_so_in_a_disabled_row(paths):
    assert paths.group.paths == () and len(paths.group._rows) == 1
    assert not paths.group._rows[0].get_sensitive()


def test_adding_a_path_adds_a_row_once(paths):
    paths.group._add("/home/u/docs")
    paths.group._add("/home/u/docs")

    assert paths.group.paths == ("/home/u/docs",) and paths.changed == [("/home/u/docs",)]


def test_a_path_the_check_refuses_is_reported_and_not_added(paths):
    paths.group._add("/etc")

    assert paths.problems == ["Not allowed"] and paths.group.paths == () and paths.changed == []


def test_removing_a_path_empties_the_list_again(paths):
    paths.group.set_paths(("/home/u/docs", "/home/u/music"))
    remove = of_type(paths.group._rows[0], Gtk.Button)[0]

    remove.emit("clicked")

    assert paths.group.paths == ("/home/u/music",) and paths.changed == [("/home/u/music",)]


def test_the_add_buttons_open_the_choosers(paths, monkeypatch):
    opened = []
    monkeypatch.setattr(
        path_list, "choose_folder", lambda window, title, on_chosen: opened.append(("folder", on_chosen))
    )
    monkeypatch.setattr(path_list, "choose_file", lambda window, title, on_chosen: opened.append(("file", on_chosen)))

    for button in of_type(paths.group.get_header_suffix(), Gtk.Button):
        button.emit("clicked")
    opened[0][1]("/home/u/a")
    opened[1][1]("/home/u/b.txt")

    assert [kind for kind, _on in opened] == ["folder", "file"]
    assert paths.group.paths == ("/home/u/a", "/home/u/b.txt")


def test_a_list_of_folders_only_has_no_button_for_files():
    group = PathListGroup(None, "Folders", "Which", "Nothing", lambda paths: None, lambda problem: None)

    assert len(of_type(group.get_header_suffix(), Gtk.Button)) == 1
