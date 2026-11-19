"""The previous-versions window: a file's timeline and a folder's browser, driven through a stand-in client."""

import time

import pytest
from gtk_helpers import of_type
from gi.repository import Adw, Gtk

from delta.ui import version_preview, versions_window
from delta.ui.versions_window import VersionsWindow

OLD = 1_700_000_000


@pytest.fixture
def app():
    return Adw.Application(application_id="io.github.sincorchetes.DeltaVersionsTests")


@pytest.fixture
def note(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("today")
    return path


@pytest.fixture
def unpacked(tmp_path):
    path = tmp_path / "unpacked" / "note.txt"
    path.parent.mkdir()
    path.write_text("what it said before")
    return path


@pytest.fixture
def folder(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "inside.txt").write_text("hello")
    (root / "sub").mkdir()
    return root


def file_versions():
    now = int(time.time())
    return [
        {"name": "s2", "time": now - 60, "mtime": OLD + 100, "size": 12, "is_dir": False},
        {"name": "s1", "time": now - 3600, "mtime": OLD, "size": 10, "is_dir": False},
    ]


def folder_versions():
    return [{**row, "is_dir": True} for row in file_versions()]


def listing():
    return [
        {"name": "inside.txt", "is_dir": False, "size": 5, "mtime": OLD},
        {"name": "gone.txt", "is_dir": False, "size": 9, "mtime": OLD},
        {"name": "sub", "is_dir": True, "size": 0, "mtime": OLD},
    ]


def open_window(app, client, path):
    window = VersionsWindow(app, client, str(path))
    window.toasts = []
    window._toasts.add_toast = window.toasts.append
    return window


def finish_preview(client, unpacked, job="preview"):
    client.answer("preview_version", job, None)
    client.subscriptions["on_backup_finished"](job, True, str(unpacked))


class Launcher:
    launched = []

    def __init__(self, gfile):
        self.gfile = gfile

    @classmethod
    def new(cls, gfile):
        return cls(gfile)

    def launch(self, window, cancellable, callback):
        Launcher.launched.append(("launch", self.gfile.get_path()))

    def open_containing_folder(self, window, cancellable, callback):
        Launcher.launched.append(("containing", self.gfile.get_path()))


class GtkWithOurLauncher:
    """Gtk, except that nothing is ever handed to the desktop: the launcher only takes notes."""

    FileLauncher = Launcher

    def __getattr__(self, name):
        return getattr(Gtk, name)


@pytest.fixture
def launcher(monkeypatch):
    Launcher.launched = []
    monkeypatch.setattr(version_preview, "Gtk", GtkWithOurLauncher())
    monkeypatch.setattr(versions_window, "Gtk", GtkWithOurLauncher())
    return Launcher


def row_named(window, name):
    names = [row.name for row in window._browser._shown]
    return window._browser._list.get_row_at_index(names.index(name))


def revert_button(row):
    return next(b for b in of_type(row, Gtk.Button) if b.get_icon_name() == "document-revert-symbolic")


# --- listing ---------------------------------------------------------------------------------------


def test_the_window_asks_for_the_versions_of_its_item(app, client, note):
    window = open_window(app, client, note)

    assert client.asked("list_versions") == [(str(note),)] and window._stack.get_visible_child_name() == "loading"


def test_a_daemon_error_is_explained(app, client, note):
    window = open_window(app, client, note)

    client.answer("list_versions", None, "the repository is locked")

    assert window._empty.get_title() == "Could not read the backups"


def test_an_item_that_is_in_no_backup_says_so(app, client, note):
    window = open_window(app, client, note)

    client.answer("list_versions", [], None)

    assert window._empty.get_title() == "No earlier versions"


def test_the_newest_version_of_a_file_is_chosen_and_asked_to_be_previewed(app, client, note):
    window = open_window(app, client, note)

    client.answer("list_versions", file_versions(), None)

    assert window._stack.get_visible_child_name() == "list" and window._shown.get_visible_child_name() == "preview"
    assert client.asked("preview_version") == [("s2", str(note))]
    assert not window._copy.get_sensitive()  # the preview job is running


# --- looking at a file -----------------------------------------------------------------------------


@pytest.fixture
def viewing(app, client, note, unpacked):
    window = open_window(app, client, note)
    client.answer("list_versions", file_versions(), None)
    finish_preview(client, unpacked)
    return window


def test_when_the_preview_arrives_the_text_is_shown_and_the_buttons_come_alive(viewing):
    assert viewing._pane.get_visible_child_name() == "text"
    assert viewing._copy.get_sensitive() and viewing._replace.get_sensitive() and viewing._open.get_sensitive()
    assert not viewing._bar.get_visible()


def test_choosing_an_older_version_previews_that_one(viewing, client, unpacked):
    viewing._timeline.step(1)

    assert client.asked("preview_version")[-1] == ("s1", str(viewing._path))


def test_restoring_as_a_copy_runs_a_job_and_says_where_it_went(viewing, client, note):
    viewing._copy.emit("clicked")
    assert client.asked("restore_as_copy") == [("s2", str(note))] and not viewing._copy.get_sensitive()

    client.answer("restore_as_copy", "job", None)
    client.subscriptions["on_backup_finished"]("job", True, str(note) + ".restored")

    assert len(viewing.toasts) == 1 and viewing._copy.get_sensitive()


def test_the_toast_after_a_restore_can_show_the_file_in_the_file_manager(viewing, client, note, launcher):
    viewing._copy.emit("clicked")
    client.answer("restore_as_copy", "job", None)
    client.subscriptions["on_backup_finished"]("job", True, str(note) + ".restored")

    viewing.toasts[0].emit("button-clicked")

    assert launcher.launched == [("containing", str(note) + ".restored")]


def test_a_restore_that_failed_is_said_without_a_button(viewing, client):
    viewing._copy.emit("clicked")
    client.answer("restore_as_copy", "job", None)

    client.subscriptions["on_backup_finished"]("job", False, "disk full")

    assert len(viewing.toasts) == 1 and viewing.toasts[0].get_button_label() in (None, "")


def test_replacing_asks_first_and_only_a_yes_goes_ahead(viewing, client, dialogs):
    viewing._replace.emit("clicked")
    dialogs.respond("cancel")
    assert client.asked("restore_replace") == []

    viewing._replace.emit("clicked")
    dialogs.respond("replace")

    assert len(client.asked("restore_replace")) == 1


def test_opening_hands_the_unpacked_file_to_its_own_application(viewing, launcher):
    viewing._open.emit("clicked")

    assert launcher.launched[0][0] == "launch"


def test_opening_while_a_job_runs_does_nothing(viewing, client, launcher):
    viewing._copy.emit("clicked")

    viewing._on_open(None)

    assert launcher.launched == []


def test_nothing_is_restored_while_another_job_runs(viewing, client):
    viewing._copy.emit("clicked")

    viewing._restore(replace=False)
    viewing._on_row_restore(["/somewhere"], False)

    assert len(client.asked("restore_as_copy")) == 1


def test_with_no_version_chosen_there_is_nothing_to_act_on(viewing, client):
    asked = len(client.requests)

    viewing._timeline._list.unselect_all()
    viewing._restore(replace=False)
    viewing._on_inner_file("/x", 1)
    viewing._on_restore_deleted()

    assert viewing._current() is None and viewing._restore_targets() == []
    assert not viewing._open.get_sensitive() and len(client.requests) == asked


def test_after_deleted_items_came_back_a_file_window_has_nothing_to_refresh(viewing, client):
    viewing._after_deleted()

    assert client.asked("list_changed") == []


def test_the_keyboard_shortcuts_step_through_versions_and_go_back(viewing):
    controller = next(
        c for c in (viewing.observe_controllers().get_item(i) for i in range(viewing.observe_controllers().get_n_items()))
        if isinstance(c, Gtk.ShortcutController)
    )

    for index in range(controller.get_n_items()):
        controller.get_item(index).get_action().activate(Gtk.ShortcutActionFlags.EXCLUSIVE, viewing, None)


def test_the_browse_button_opens_the_chosen_backup_and_shows_it_in_files(viewing, client, launcher, note):
    client.answer("read_state", {"CanMount": True}, None)
    assert viewing._folder.button.get_visible() and viewing._folder.button.get_sensitive()

    viewing._folder.button.emit("clicked")
    client.answer("mount_snapshot", "job1", None)
    viewing._tracker.on_finished("job1", True, "/run/browse/snapshot")

    assert client.asked("mount_snapshot") == [("s2",)]
    assert launcher.launched == [("containing", "/run/browse/snapshot" + str(note))]


def test_closing_the_window_closes_the_folder_it_opened(viewing, client):
    client.answer("read_state", {"CanMount": True}, None)
    viewing._folder._opened = True

    viewing._on_close(viewing)

    assert client.asked("unmount_snapshot") == [()]


def test_closing_lets_go_of_everything(viewing, client):
    assert viewing._on_close(viewing) is False

    assert client.unsubscribed and client.asked("clear_previews") == [()]


# --- inside a folder -------------------------------------------------------------------------------


@pytest.fixture
def browsing(app, client, folder):
    window = open_window(app, client, folder)
    client.answer("list_versions", folder_versions(), None)
    client.answer("list_folder", listing(), None)
    return window


def test_a_folder_version_opens_the_browser_at_the_folder(browsing, client, folder):
    assert browsing._shown.get_visible_child_name() == "browser"
    assert client.asked("list_folder") == [("s2", str(folder))] and browsing._bar.get_visible()
    assert not browsing._back.get_sensitive()


def test_opening_a_file_inside_shows_it_and_back_returns_to_the_list(browsing, client, folder):
    browsing._browser._list.emit("row-activated", row_named(browsing, "inside.txt"))

    assert browsing._inner is not None and browsing._shown.get_visible_child_name() == "preview"
    assert client.asked("preview_version")[-1] == ("s2", str(folder / "inside.txt")) and browsing._back.get_sensitive()

    browsing._on_back(None)
    assert browsing._inner is None and browsing._shown.get_visible_child_name() == "browser"


def test_back_in_a_subfolder_goes_up_a_level(browsing, client, folder):
    browsing._browser._list.emit("row-activated", row_named(browsing, "sub"))
    assert browsing._back.get_sensitive() and "sub" in browsing._where.get_label()

    browsing._on_back(None)

    assert client.asked("list_folder")[-1] == ("s2", str(folder))


def test_choosing_an_older_folder_version_reopens_the_browser_for_it(browsing, client, folder):
    browsing._timeline.step(1)

    assert client.asked("list_folder")[-1] == ("s1", str(folder))


def test_the_row_button_restores_without_asking_a_deleted_item_in_place_and_a_changed_one_as_a_copy(
    browsing, client, folder
):
    revert_button(row_named(browsing, "gone.txt")).emit("clicked")
    assert client.asked("restore_replace") == [("s2", str(folder / "gone.txt"))]
    client.answer("restore_replace", "job", None)
    client.subscriptions["on_backup_finished"]("job", True, str(folder / "gone.txt"))

    revert_button(row_named(browsing, "inside.txt")).emit("clicked")

    assert client.asked("restore_as_copy") == [("s2", str(folder / "inside.txt"))]


def test_several_ticked_items_are_restored_one_after_another_deleted_ones_in_place(browsing, client, folder):
    browsing._browser._select.set_active(True)
    for name in ("inside.txt", "gone.txt"):
        browsing._browser._checks[name].set_active(True)
    assert "2" in browsing._copy.get_label() and "2" in browsing._replace.get_label()

    browsing._copy.emit("clicked")
    assert client.asked("restore_replace") == [("s2", str(folder / "gone.txt"))]  # deleted: back under its own name
    client.answer("restore_replace", "job1", None)
    client.subscriptions["on_backup_finished"]("job1", True, str(folder / "gone.txt"))

    assert client.asked("restore_as_copy") == [("s2", str(folder / "inside.txt"))]
    client.answer("restore_as_copy", "job2", None)
    client.subscriptions["on_backup_finished"]("job2", True, str(folder / "inside (restored).txt"))
    assert len(browsing.toasts) == 1


def test_with_nothing_ticked_in_selection_mode_nothing_can_be_restored(browsing):
    browsing._browser._select.set_active(True)

    assert browsing._restore_targets() == [] and not browsing._copy.get_sensitive()


def test_a_finished_restore_marks_the_rows_and_refreshes_the_comparison(browsing, client, folder):
    browsing._browser._select.set_active(True)
    browsing._browser._checks["inside.txt"].set_active(True)
    browsing._copy.emit("clicked")
    client.answer("restore_as_copy", "job", None)

    client.subscriptions["on_backup_finished"]("job", True, str(folder / "inside (restored).txt"))

    assert len(browsing.toasts) == 1 and len(client.asked("list_changed")) >= 2


def test_restore_deleted_asks_for_what_is_gone_and_refreshes_after(browsing, client, folder, dialogs):
    browsing._on_restore_deleted()
    assert client.asked("list_deleted") == [("s2", str(folder))]

    client.answer("list_deleted", [{"name": "gone.txt", "size": 9, "is_dir": False, "mtime": OLD}], None)
    dialogs.respond("restore")
    client.answer("restore_deleted", "job", None)
    client.subscriptions["on_backup_finished"]("job", True, "1")

    assert len(browsing.toasts) == 1 and len(client.asked("list_changed")) >= 2


def test_coming_back_to_the_window_refreshes_what_the_comparison_says(browsing, client):
    before = len(client.asked("list_changed"))
    browsing.is_active = lambda: True

    browsing._on_active(browsing, None)

    assert len(client.asked("list_changed")) == before + 1


def test_an_inactive_window_does_not_refresh(browsing, client):
    before = len(client.asked("list_changed"))

    browsing._on_active(browsing, None)

    assert len(client.asked("list_changed")) == before


def test_a_file_version_does_not_refresh_on_activation(app, client, note):
    window = open_window(app, client, note)
    window.is_active = lambda: True
    client.answer("list_versions", file_versions(), None)

    window._on_active(window, None)

    assert client.asked("list_changed") == []


def test_a_restore_toast_needs_the_item_to_be_named_when_replacing(app, client, note, unpacked):
    window = open_window(app, client, note)
    client.answer("list_versions", file_versions(), None)
    finish_preview(client, unpacked)

    window._start_batch("s2", [(str(note), True)])
    client.answer("restore_replace", "job", None)
    client.subscriptions["on_backup_finished"]("job", True, str(note))

    assert len(window.toasts) == 1
