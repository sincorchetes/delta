"""What the pane of a version asks first, what it makes wait, and what it says when something fails."""

from types import SimpleNamespace
from delta.ui import version_preview
from delta.ui.preview_kind import AUTO_IMAGE_MAX, AUTO_MEDIA_MAX
from version_preview_support import AUDIO, Launcher, Setup, TAG, finished_with, play_mp3
from gi.repository import GLib, Gtk


def test_a_big_video_asks_before_being_unpacked():
    s = Setup("/home/u/film.mp4")
    s.select(s.target("a", size=AUTO_MEDIA_MAX + 1))
    assert s.client.requests == [] and s.pane.events[-1][:2] == ("action", "Large file")


def test_media_the_player_cannot_decode_falls_back_to_its_own_application():
    s = Setup("/home/u/clip.mp4")
    s.select(s.target("a"))
    s.finish("j1", message="/run/preview/a/clip.mp4")

    s.pane.media_error()

    assert s.pane.events[-1][:2] == ("action", "clip.mp4")


def test_a_late_media_error_of_a_target_no_longer_current_is_ignored():
    s = Setup("/home/u/clip.mp4")
    s.select(s.target("a"))
    s.finish("j1", message="/run/preview/a/clip.mp4")
    s.current = s.target("b")
    shown = len(s.pane.events)

    s.pane.media_error()

    assert len(s.pane.events) == shown


def test_a_big_image_asks_before_being_unpacked():
    s = Setup()
    s.select(s.target("a", size=AUTO_IMAGE_MAX + 1))

    assert s.client.requests == [] and s.pane.events[-1][:2] == ("action", "Large file")
    s.pane.events[-1][2]()  # the user agrees

    assert s.client.requests == [("a", "/home/u/photo.jpg")]


def test_a_file_only_its_own_application_can_show_is_not_unpacked():
    s = Setup("/home/u/doc.pdf")
    s.select(s.target("a"))
    assert s.client.requests == [] and s.pane.events[-1][0] == "action"


def test_a_folder_is_not_unpacked_just_by_selecting_it():
    s = Setup("/home/u/Pictures")
    s.select(s.target("a", is_dir=True))
    assert s.client.requests == [] and s.pane.events[-1][0] == "action"


def test_a_target_already_unpacked_is_not_unpacked_again():
    s = Setup()
    s.select(s.target("a"))
    s.finish("j1", message="/run/preview/a/photo.jpg")

    s.select(s.target("a"))

    assert len(s.client.requests) == 1
    assert s.pane.events[-1] == ("image", "/run/preview/a/photo.jpg")


def test_a_target_picked_while_another_unpacks_waits_its_turn():
    s = Setup()
    s.select(s.target("a"))
    s.select(s.target("b"))

    assert s.client.requests == [("a", "/home/u/photo.jpg")]
    s.finish("j1", message="/run/preview/a/photo.jpg")

    assert s.client.requests[-1] == ("b", "/home/u/photo.jpg")
    assert ("image", "/run/preview/a/photo.jpg") not in s.pane.events  # a is no longer current


def test_only_the_latest_pick_is_unpacked_after_the_wait():
    s = Setup()
    s.select(s.target("a"))
    s.select(s.target("b"))
    s.select(s.target("c"))

    s.finish("j1")

    assert [snapshot for snapshot, _ in s.client.requests] == ["a", "c"]


def test_a_failure_is_said_in_the_pane():
    s = Setup()
    s.select(s.target("a"))
    s.finish("j1", ok=False, message="another job is already running")
    assert s.pane.events[-1] == ("message", "Could not show this version")


def test_a_failure_opening_outside_is_said_in_a_toast():
    s = Setup()
    s.current = s.target("a")
    s.previewer.open_outside(s.current)
    s.finish("j1", ok=False, message="boom")
    assert len(s.toasts) == 1


def test_closing_when_no_copy_was_made_is_harmless():
    Setup().previewer.close()


def test_a_failure_for_something_no_longer_selected_shows_nothing():
    s = Setup()
    s.select(s.target("a"))
    s.current = s.target("b")

    s.finish("j1", ok=False, message="boom")

    assert not any(event[0] == "message" for event in s.pane.events)


def test_an_image_the_window_cannot_show_is_offered_to_its_own_application():
    s = Setup()
    s.pane.show_image = lambda path: False
    s.select(s.target("a"))

    s.finish("j1", message="/run/preview/a/photo.jpg")

    assert s.pane.events[-1][0] == "action"


def test_a_second_mp3_reuses_the_folder_made_for_the_first(tmp_path):
    s, _unpacked = play_mp3(tmp_path, TAG + AUDIO)
    first = s.previewer._scratch
    other = tmp_path / "other.mp3"
    other.write_bytes(TAG + AUDIO)

    s.select(s.target("b"))
    s.finish("j2", message=str(other))

    assert s.previewer._scratch == first


def test_opening_outside_hands_the_unpacked_file_to_its_own_application(monkeypatch):
    Launcher.launched = []
    monkeypatch.setattr(version_preview, "Gtk", SimpleNamespace(FileLauncher=Launcher))
    s = Setup()
    s.current = s.target("a")

    s.previewer.open_outside(s.current)
    s.finish("j1", message="/run/preview/a/photo.jpg")

    assert [path for path, _callback in Launcher.launched] == ["/run/preview/a/photo.jpg"]


def test_an_application_that_opened_the_file_needs_no_word_about_it():
    s = Setup()

    s.previewer._launched(finished_with(None), None)

    assert s.toasts == []


def test_choosing_no_application_is_not_an_error_to_report():
    s = Setup()
    dismissed = GLib.Error(
        "Dismissed by user",
        domain=GLib.quark_to_string(Gtk.dialog_error_quark()),
        code=int(Gtk.DialogError.DISMISSED),
    )

    s.previewer._launched(finished_with(dismissed), None)

    assert s.toasts == []


def test_no_application_to_open_the_file_is_said_in_a_toast_and_the_reason_is_logged(caplog):
    s = Setup()

    with caplog.at_level("WARNING"):
        s.previewer._launched(finished_with(GLib.Error("No application", domain="test", code=1)), None)

    assert s.toasts == ["No application could open this version."]
    assert "cannot open the version with another application: No application" in caplog.text
