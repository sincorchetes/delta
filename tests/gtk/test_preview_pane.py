"""The preview pane, as a real widget."""

from types import SimpleNamespace
from gtk_helpers import of_type
from gi.repository import GLib, Gtk
from delta.ui.preview_pane import read_text_head
from panes_and_dialogs_support import PNG, silence
from panes_and_dialogs_support import pane  # noqa: F401  (fixtures)


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
    text.write_text("héllo", encoding="utf-8")

    assert read_text_head(str(text)) == "héllo"
    assert read_text_head(str(tmp_path / "missing")) is None


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
