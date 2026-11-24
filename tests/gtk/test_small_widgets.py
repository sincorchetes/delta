"""Shortcuts, the timeline, folder rows and the wizard's building blocks, as real widgets."""

from types import SimpleNamespace

import pytest
from gtk_helpers import labels, of_type
from gi.repository import Adw, Gio, GLib, Gtk

from delta.ui import path_list, shortcuts, wizard_base, wizard_destination
from delta.ui.folder_listing import Change, FolderRow, change_label
from delta.ui.folder_row import build_row, cap_notice_row
from delta.ui.path_list import PathListGroup
from delta.ui.timeline import Timeline
from delta.ui.versions import VersionRow
from delta.ui.wizard import WizardModel
from delta.ui.wizard_base import Page, choose_file, choose_folder, flat_icon_button
from delta.ui.wizard_destination import DestinationPage

# --- shortcuts -----------------------------------------------------------------------------------


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


# --- timeline ------------------------------------------------------------------------------------


def version(n):
    return VersionRow(snapshot=f"s{n}", modified=f"2026-01-0{n}", backed_up=f"Backed up {n}", size=n)


@pytest.fixture
def chosen():
    return []


@pytest.fixture
def opened():
    return []


@pytest.fixture
def line(chosen, opened):
    widget = Timeline(chosen.append, lambda: opened.append(True))
    widget.fill([version(3), version(2), version(1)])
    return widget


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


# --- folder rows ---------------------------------------------------------------------------------


def entry(change=Change.MODIFIED, is_dir=False, name="photo.jpg"):
    return FolderRow(name=name, is_dir=is_dir, size=10, mtime=1, detail="10 bytes", change=change)


def restore_button(row):
    return next(b for b in of_type(row, Gtk.Button) if b.get_icon_name() == "document-revert-symbolic")


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
    row, _check = build_row(entry(Change.UNKNOWN, is_dir=True, name="Pictures"), False, False, lambda on: None, lambda: None)

    assert "go-next-symbolic" in [image.get_icon_name() for image in of_type(row, Gtk.Image)]


def test_a_search_that_hit_the_limit_says_how_many_are_shown():
    assert "1000" in cap_notice_row(1000).get_title()


# --- the wizard's building blocks ----------------------------------------------------------------


class Dialog:
    last = None

    def __init__(self, title):
        self.title, self.callback, self.initial = title, None, None
        Dialog.last = self

    def set_initial_folder(self, folder):
        self.initial = folder.get_path()

    def select_folder(self, window, cancellable, callback):
        self.callback = callback

    def open(self, window, cancellable, callback):
        self.callback = callback

    def select_folder_finish(self, result):
        if isinstance(result, GLib.Error):
            raise result
        return result

    open_finish = select_folder_finish


@pytest.fixture
def file_dialog(monkeypatch):
    monkeypatch.setattr(wizard_base, "Gtk", SimpleNamespace(FileDialog=Dialog))
    return Dialog


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


# --- the destination page ------------------------------------------------------------------------


def Drive():
    return SimpleNamespace(
        name="Backup disk", mount_point="/run/media/u/disk", suggested_folder="/run/media/u/disk/delta-backups"
    )


def destination_page(monkeypatch, drives=()):
    monkeypatch.setattr(wizard_destination, "removable_drives", lambda mounts: list(drives))
    model = WizardModel(home="/home/u", inspect=lambda path: None)
    changes = []
    return DestinationPage(model, None, lambda: changes.append(model.destination)), model, changes


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
        wizard_destination, "choose_folder", lambda window, title, on_chosen, start: (asked.append(start), on_chosen("/media/disk"))
    )
    model.destination = "~/Backups/new"
    start = model.chooser_start()

    page._on_choose(None)

    assert model.destination == "/media/disk" and asked == [start]


# --- a list of paths -----------------------------------------------------------------------------


@pytest.fixture
def paths():
    seen = SimpleNamespace(changed=[], problems=[])
    seen.group = PathListGroup(
        None, "Folders", "Which folders", "Nothing chosen", seen.changed.append, seen.problems.append,
        allow_files=True, check=lambda path: "Not allowed" if path == "/etc" else None,
    )
    return seen


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
    monkeypatch.setattr(path_list, "choose_folder", lambda window, title, on_chosen: opened.append(("folder", on_chosen)))
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
