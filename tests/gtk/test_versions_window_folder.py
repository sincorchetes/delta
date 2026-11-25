"""The previous-versions window of a folder: its browser and its restores."""

from versions_window_support import OLD, file_versions, finish_preview, open_window, revert_button, row_named
from versions_window_support import app, browsing, folder, note, unpacked  # noqa: F401  (fixtures)


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
