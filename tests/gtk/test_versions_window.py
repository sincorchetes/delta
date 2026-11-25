"""The previous-versions window of a file: its timeline, preview and restores, driven through a stand-in client."""

from gi.repository import Gtk
from versions_window_support import file_versions, open_window
from versions_window_support import app, launcher, note, unpacked, viewing  # noqa: F401  (fixtures)


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
        c
        for c in (viewing.observe_controllers().get_item(i) for i in range(viewing.observe_controllers().get_n_items()))
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
