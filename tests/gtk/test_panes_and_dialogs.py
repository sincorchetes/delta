"""The preview pane, the preferences, the history window and the restore-deleted flow, as real widgets."""

import base64
import wave
from types import SimpleNamespace

import pytest
from conftest import of_type
from gi.repository import Adw, GLib, GObject, Gtk

from delta.i18n import _
from delta.ui import history_window
from delta.ui.history_window import HistoryWindow, Row, _column
from delta.ui.job_tracker import JobTracker
from delta.ui.preferences_dialog import PreferencesDialog
from delta.ui.preview_pane import PreviewPane, read_text_head
from delta.ui.restore_deleted import RestoreDeleted, confirm_replace

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


# --- the preview pane ----------------------------------------------------------------------------


@pytest.fixture
def pane():
    return PreviewPane()


def test_the_pane_starts_empty_and_can_show_loading(pane):
    assert pane.get_visible_child_name() == "status"

    pane.show_loading()

    assert pane.get_visible_child_name() == "loading"


def test_a_message_replaces_whatever_was_shown(pane):
    pane.show_message("Could not <show>", "Because & so", "dialog-error-symbolic")

    assert pane.get_visible_child_name() == "status"
    assert pane._status.get_title() == "Could not &lt;show&gt;"
    assert pane._status.get_child() is None


def test_a_message_with_an_action_has_a_button_that_runs_it(pane):
    clicked = []

    pane.show_action("A folder", "Open it", "Open", lambda: clicked.append(True))
    of_type(pane._status, Gtk.Button)[0].emit("clicked")

    assert clicked == [True]


def test_an_image_is_shown_and_something_else_is_refused(pane, tmp_path):
    good, bad = tmp_path / "a.png", tmp_path / "a.txt"
    good.write_bytes(PNG)
    bad.write_text("not an image")

    assert pane.show_image(str(good)) is True and pane.get_visible_child_name() == "image"
    assert pane.show_image(str(bad)) is False


def test_text_is_shown_and_binary_or_unreadable_files_are_refused(pane, tmp_path):
    text, binary = tmp_path / "a.txt", tmp_path / "a.bin"
    text.write_text("hello\nworld")
    binary.write_bytes(b"\x00\x01\x02" * 100)

    assert pane.show_text(str(text)) is True and pane.get_visible_child_name() == "text"
    assert pane._text.get_buffer().get_text(*pane._text.get_buffer().get_bounds(), False) == "hello\nworld"
    assert pane.show_text(str(binary)) is False
    assert pane.show_text(str(tmp_path / "missing")) is False


def test_reading_the_head_of_a_file(tmp_path):
    text = tmp_path / "a.txt"
    text.write_text("héllo")

    assert read_text_head(str(text)) == "héllo"
    assert read_text_head(str(tmp_path / "missing")) is None


def silence(path):
    """A real, valid audio file: a tenth of a second of nothing."""
    with wave.open(str(path), "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(8000)
        sound.writeframes(b"\x00\x00" * 800)
    return path


def test_media_is_shown_paused_and_stopped_before_anything_else(pane, tmp_path):
    pane.show_media(str(silence(tmp_path / "clip.wav")), lambda: None)
    assert pane.get_visible_child_name() == "media" and pane._media is not None

    pane.show_loading()
    assert pane._media is None


def test_a_player_that_reports_an_error_calls_for_the_fallback(pane, tmp_path):
    failed = []
    broken = SimpleNamespace(get_error=lambda: GLib.Error("no codec", domain="test", code=1))
    fine = SimpleNamespace(get_error=lambda: None)

    pane._media_error(fine, str(tmp_path / "a.mp4"), lambda: failed.append("fine"))
    pane._media_error(broken, str(tmp_path / "a.mp4"), lambda: failed.append("broken"))

    assert failed == ["broken"]


def test_the_players_own_error_signal_is_followed(pane, tmp_path):
    pane.show_media(str(silence(tmp_path / "clip.wav")), lambda: None)

    pane._media.notify("error")

    pane.stop_media()


# --- the preferences -----------------------------------------------------------------------------


class Settings:
    def __init__(self, **values):
        self.values = {
            "repository-location": "/media/disk/delta-backups",
            "schedule": "hourly",
            "keep-hourly": 24, "keep-daily": 7, "keep-weekly": 4, "keep-monthly": 12,
            "backup-sources": [], "excluded-paths": [],
        }
        self.values.update(values)
        self.written = []

    def get_string(self, key):
        return self.values[key]

    get_int = get_strv = get_string

    def _set(self, key, value):
        self.written.append((key, value))
        self.values[key] = value

    set_string = set_int = set_strv = _set


def preferences(**values):
    settings = Settings(**values)
    dialog = PreferencesDialog(settings, "/home/u", None)
    toasts = []
    dialog.add_toast = toasts.append
    return dialog, settings, toasts


def test_the_destination_is_shown():
    dialog, _settings, _toasts = preferences()

    assert any("/media/disk/delta-backups" in (row.get_subtitle() or "") for row in of_type(dialog.get_visible_page(), Adw.ActionRow))


def test_without_a_destination_it_says_so():
    dialog, _settings, _toasts = preferences(**{"repository-location": ""})

    assert any(row.get_subtitle() == _("Not set up yet") for row in of_type(dialog.get_visible_page(), Adw.ActionRow))


def test_choosing_another_schedule_is_saved():
    dialog, settings, _toasts = preferences()

    dialog._schedule.set_selected(1)

    assert settings.written == [("schedule", "daily")]


def test_the_schedule_already_in_force_is_not_written_again():
    dialog, settings, _toasts = preferences()

    dialog._on_schedule(dialog._schedule, None)

    assert settings.written == []


def test_a_schedule_set_by_hand_is_not_overwritten_by_looking_at_it():
    dialog, settings, _toasts = preferences(schedule="*-*-* 03:00:00")

    dialog._schedule.set_selected(3)  # the "Custom" entry stands for what is already set

    assert settings.written == []


def checks(dialog):
    return of_type(dialog.get_visible_page(), Gtk.CheckButton)


def test_choosing_a_retention_option_saves_its_four_values():
    dialog, settings, _toasts = preferences()

    checks(dialog)[2].set_active(True)  # "Long": 24, 14, 12, 36

    assert dict(settings.written) == {"keep-daily": 14, "keep-weekly": 12, "keep-monthly": 36}
    assert [key for key, _value in settings.written if key == "keep-hourly"] == []


def test_the_option_in_force_is_ticked_and_a_hand_set_value_gets_its_own_row():
    dialog, _settings, _toasts = preferences(**{"keep-daily": 9})

    boxes = checks(dialog)

    assert len(boxes) == 4 and boxes[3].get_active() and not boxes[3].get_sensitive()
    assert not any(box.get_active() for box in boxes[:3])


def test_unticking_an_option_changes_nothing():
    dialog, settings, _toasts = preferences()

    dialog._on_preset(checks(dialog)[0], 0)
    dialog._on_preset(checks(dialog)[1], 99)

    assert settings.written == []


def test_chosen_folders_and_exclusions_are_saved_as_lists():
    dialog, settings, _toasts = preferences()

    dialog._sources._add("/home/u/docs")
    dialog._exclusions._add("/home/u/docs/tmp")

    assert ("backup-sources", ["/home/u/docs"]) in settings.written
    assert ("excluded-paths", ["/home/u/docs/tmp"]) in settings.written


def test_an_exclusion_that_would_skip_everything_is_refused_with_a_toast():
    dialog, settings, toasts = preferences()

    dialog._exclusions._add("/home/u")

    assert len(toasts) == 1 and settings.written == []


# --- the history ---------------------------------------------------------------------------------


def test_the_history_waits_for_the_daemon_then_lists_the_backups(client):
    window = HistoryWindow(None, client)
    assert window._stack.get_visible_child_name() == "loading"

    client.answer("list_snapshots", [{"id": "1", "name": "first", "time": 1_700_000_000},
                                     {"id": "2", "name": "second", "time": 1_700_100_000}], None)

    assert window._stack.get_visible_child_name() == "list"
    assert window._store.get_n_items() == 2 and window._count.get_text() == "2 backups"
    assert window._store.get_item(0).name == "second"  # newest first


def test_an_empty_repository_says_there_are_no_backups_yet(client):
    window = HistoryWindow(None, client)

    client.answer("list_snapshots", [], None)

    assert window._stack.get_visible_child_name() == "empty" and window._empty.get_title() == "No backups yet"


def test_a_daemon_error_is_explained(client):
    window = HistoryWindow(None, client)

    client.answer("list_snapshots", None, "the repository is locked")

    assert window._empty.get_title() == "Could not read the backups"
    assert "locked" in window._empty.get_description()


def test_the_table_cells_show_the_chosen_attribute(monkeypatch):
    handlers = {}

    def recording_connect(self, name, handler):
        handlers[name] = handler
        return GObject.Object.connect(self, name, handler)

    monkeypatch.setattr(Gtk.SignalListItemFactory, "connect", recording_connect)
    column = _column("Date", "when")
    cell = {}
    item = SimpleNamespace(
        set_child=lambda child: cell.update(child=child),
        get_child=lambda: cell["child"],
        get_item=lambda: Row(name="n", when="2026-01-01  10:00", ago="2 days ago"),
    )

    handlers["setup"](column.get_factory(), item)
    handlers["bind"](column.get_factory(), item)

    assert cell["child"].get_text() == "2026-01-01  10:00" and column.get_title() == "Date"


def test_the_history_module_builds_rows_from_history_rows():
    row = Row.of(SimpleNamespace(name="a", when="b", ago="c"))

    assert (row.name, row.when, row.ago) == ("a", "b", "c") and history_window.Row is Row


# --- restoring what was deleted ------------------------------------------------------------------


@pytest.fixture
def restoring(client):
    seen = SimpleNamespace(toasts=[], changes=0, done=0)
    tracker = JobTracker()
    flow = RestoreDeleted(
        client, tracker, None, seen.toasts.append,
        lambda: setattr(seen, "changes", seen.changes + 1), lambda: setattr(seen, "done", seen.done + 1),
    )
    seen.flow, seen.tracker = flow, tracker
    return seen


def rows(n):
    return [{"name": f"f{i}", "size": 1000, "is_dir": False, "mtime": 1} for i in range(n)]


def test_nothing_deleted_is_said_and_nothing_is_asked(restoring, client, dialogs):
    restoring.flow.start("s", "/home/u/docs")
    client.answer("list_deleted", [], None)

    assert len(restoring.toasts) == 1 and dialogs.items == []


def test_a_daemon_error_while_looking_is_reported(restoring, client, dialogs):
    restoring.flow.start("s", "/home/u/docs")
    client.answer("list_deleted", None, "locked")

    assert len(restoring.toasts) == 1 and dialogs.items == []


def test_the_user_confirms_and_the_whole_folder_comes_back_in_one_job(restoring, client, dialogs):
    restoring.flow.start("s", "/home/u/docs")
    client.answer("list_deleted", rows(3), None)
    assert "3" in dialogs.items[-1][0].get_body()

    dialogs.respond("restore")
    assert client.asked("restore_deleted") == [("s", "/home/u/docs")] and restoring.tracker.busy

    restoring.tracker.on_started("job", None)
    restoring.tracker.on_finished("job", True, "3")

    assert restoring.done == 1 and len(restoring.toasts) == 1 and not restoring.tracker.busy


def test_cancelling_restores_nothing(restoring, client, dialogs):
    restoring.flow.start("s", "/home/u/docs")
    client.answer("list_deleted", rows(2), None)

    dialogs.respond("cancel")

    assert client.asked("restore_deleted") == [] and not restoring.tracker.busy


def test_while_a_job_runs_nothing_new_is_started(restoring, client, dialogs):
    restoring.tracker.begin(lambda ok, message: None)

    restoring.flow.start("s", "/home/u/docs")

    assert client.asked("list_deleted") == []


def test_answering_yes_after_another_job_began_does_nothing(restoring, client, dialogs):
    restoring.flow.start("s", "/home/u/docs")
    client.answer("list_deleted", rows(1), None)
    restoring.tracker.begin(lambda ok, message: None)

    dialogs.respond("restore")

    assert client.asked("restore_deleted") == []


@pytest.mark.parametrize(("count", "heading"), [(1, "Replace the current version?"), (3, "Replace 3 current versions?")])
def test_replacing_asks_first_and_only_a_yes_goes_ahead(dialogs, count, heading):
    yes = []

    confirm_replace(None, count, lambda: yes.append(True))
    assert dialogs.items[-1][0].get_heading() == heading
    dialogs.respond("cancel")
    dialogs.respond("replace")

    assert yes == [True]
