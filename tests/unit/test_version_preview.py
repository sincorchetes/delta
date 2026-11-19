import pytest

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio, GLib, Gtk
except (ValueError, ImportError):
    pytest.skip("GTK 4 is not available", allow_module_level=True)

from types import SimpleNamespace

from delta.ui import version_preview
from delta.ui.job_tracker import JobTracker
from delta.ui.preview_kind import AUTO_IMAGE_MAX, AUTO_MEDIA_MAX
from delta.ui.version_preview import Target, VersionPreviewer

if Gio.content_type_guess("a.jpg", None)[0] != "image/jpeg":
    pytest.skip("no shared-mime-info database", allow_module_level=True)


class FakeClient:
    def __init__(self):
        self.requests = []

    def preview_version(self, snapshot, path, reply):
        self.requests.append((snapshot, path))


class FakePane:
    def __init__(self):
        self.events = []

    def show_loading(self):
        self.events.append(("loading",))

    def show_message(self, title, detail, icon=""):
        self.events.append(("message", title))

    def show_action(self, title, detail, label, callback, icon=""):
        self.events.append(("action", title, callback))

    def show_image(self, path):
        self.events.append(("image", path))
        return True

    def show_text(self, path):
        self.events.append(("text", path))
        return True

    def show_media(self, path, on_error):
        self.events.append(("media", path))
        self.media_error = on_error


class FakeMedia:
    """Stands in for MediaProbe: says at once whether the player can be made, or None to wait until the test answers."""

    def __init__(self, supported: bool | None = True):
        self.supported, self.waiting = supported, []

    def check(self, then):
        if self.supported is None:
            self.waiting.append(then)
        else:
            then(self.supported)

    def answer(self, supported):
        waiting, self.waiting = self.waiting, []
        for then in waiting:
            then(supported)


class Setup:
    def __init__(self, path="/home/u/photo.jpg", scratch_root=None, media=None):
        self.path = path
        self.client, self.pane, self.tracker = FakeClient(), FakePane(), JobTracker()
        self.current = None
        self.toasts, self.changes = [], []
        self.media = media or FakeMedia()
        self.previewer = VersionPreviewer(
            self.client, self.tracker, self.pane, None,
            lambda: self.current, lambda: self.changes.append(1), self.toasts.append,
            scratch_root=scratch_root, media=self.media,
        )

    def target(self, snapshot, size=1000, is_dir=False, path=None):
        return Target(snapshot, path or self.path, size, is_dir)

    def select(self, chosen):
        self.current = chosen
        self.previewer.show(chosen)

    def finish(self, job, ok=True, message="/run/preview/x"):
        self.tracker.on_started(job, None)
        self.tracker.on_finished(job, ok, message)


def test_a_small_image_is_unpacked_and_then_shown_inside_the_window():
    s = Setup()
    s.select(s.target("a"))

    assert s.pane.events == [("loading",)] and s.client.requests == [("a", "/home/u/photo.jpg")]
    s.finish("j1", message="/run/preview/a/photo.jpg")

    assert s.pane.events[-1] == ("image", "/run/preview/a/photo.jpg")


def test_a_text_file_is_shown_as_text():
    s = Setup("/home/u/notes.txt")
    s.select(s.target("a"))
    s.finish("j1", message="/run/preview/a/notes.txt")
    assert s.pane.events[-1] == ("text", "/run/preview/a/notes.txt")


def test_a_file_inside_a_folder_is_unpacked_by_its_own_path():
    s = Setup("/home/u/Pictures")
    inside = s.target("a", path="/home/u/Pictures/sub/me.png")

    s.select(inside)

    assert s.client.requests == [("a", "/home/u/Pictures/sub/me.png")]
    s.finish("j1", message="/run/preview/a/me.png")
    assert s.pane.events[-1] == ("image", "/run/preview/a/me.png")


def test_two_files_of_one_snapshot_are_not_mistaken_for_each_other():
    s = Setup("/home/u/Pictures")
    one, two = s.target("a", path="/home/u/Pictures/1.png"), s.target("a", path="/home/u/Pictures/2.png")
    s.select(one)
    s.finish("j1", message="/run/preview/a/1.png")

    s.select(two)

    assert s.client.requests == [("a", "/home/u/Pictures/1.png"), ("a", "/home/u/Pictures/2.png")]


@pytest.mark.parametrize("name", ["clip.mp4", "song.flac", "voice.ogg"])
def test_video_and_audio_are_unpacked_and_given_to_the_player(name):
    s = Setup(f"/home/u/{name}")
    s.select(s.target("a"))
    s.finish("j1", message=f"/run/preview/a/{name}")
    assert s.pane.events[-1] == ("media", f"/run/preview/a/{name}")


AUDIO = b"\xff\xfb\x90\x00" + b"frames" * 20
TAG = b"ID3\x03\x00\x00" + bytes([0, 0, 0x0A, 0x00]) + b"\x55" * 1280  # a tag of 1280 bytes: cover art


def play_mp3(tmp_path, content, scratch=None):
    """Unpack an mp3 holding `content` and return (setup, path it was unpacked to)."""
    unpacked = tmp_path / "unpacked.mp3"
    unpacked.write_bytes(content)
    s = Setup("/home/u/song.mp3", scratch_root=str(scratch or tmp_path))
    s.select(s.target("a"))
    s.finish("j1", message=str(unpacked))
    return s, unpacked


def test_an_mp3_with_cover_art_is_played_from_a_copy_without_its_tag(tmp_path):
    s, unpacked = play_mp3(tmp_path, TAG + AUDIO)

    kind, played = s.pane.events[-1]

    assert kind == "media" and played != str(unpacked)
    assert open(played, "rb").read() == AUDIO
    assert unpacked.read_bytes() == TAG + AUDIO  # the unpacked version itself is untouched


def test_an_mp3_without_a_tag_is_played_as_it_is(tmp_path):
    s, unpacked = play_mp3(tmp_path, AUDIO)
    assert s.pane.events[-1] == ("media", str(unpacked))


def test_the_copies_made_for_the_player_are_removed_on_close(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    s, _ = play_mp3(tmp_path, TAG + AUDIO, scratch)
    assert any(scratch.iterdir())

    s.previewer.close()

    assert not any(scratch.iterdir())


def test_when_the_copy_cannot_be_made_the_mp3_goes_to_its_own_application(tmp_path):
    s, unpacked = play_mp3(tmp_path, TAG + AUDIO, scratch=tmp_path / "missing")
    assert s.pane.events[-1][0] == "action" and ("media", str(unpacked)) not in s.pane.events


def unpack_video(s, name="film.mp4"):
    s.select(s.target("a"))
    s.finish("j1", message=f"/run/preview/a/{name}")


def test_where_the_player_cannot_be_made_a_video_goes_to_its_own_application():
    # GTK ends the whole program when GStreamer cannot make it, so it must not be tried in this process.
    s = Setup("/home/u/film.mp4", media=FakeMedia(supported=False))

    unpack_video(s)

    assert s.pane.events[-1][0] == "action" and not any(event[0] == "media" for event in s.pane.events)


def test_an_mp3_is_not_even_copied_when_there_is_no_player_for_it(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    unpacked = tmp_path / "unpacked.mp3"
    unpacked.write_bytes(TAG + AUDIO)
    s = Setup("/home/u/song.mp3", scratch_root=str(scratch), media=FakeMedia(supported=False))

    s.select(s.target("a"))
    s.finish("j1", message=str(unpacked))

    assert s.pane.events[-1][0] == "action" and not any(scratch.iterdir())


def test_a_video_waits_for_the_answer_about_the_player_and_then_plays():
    media = FakeMedia(supported=None)
    s = Setup("/home/u/film.mp4", media=media)
    unpack_video(s)
    assert s.pane.events == [("loading",)]  # still the spinner: the answer has not come

    media.answer(True)

    assert s.pane.events[-1] == ("media", "/run/preview/a/film.mp4")


def test_a_video_waits_for_the_answer_and_then_goes_to_its_own_application_when_there_is_no_player():
    media = FakeMedia(supported=None)
    s = Setup("/home/u/film.mp4", media=media)
    unpack_video(s)

    media.answer(False)

    assert s.pane.events[-1][0] == "action" and not any(event[0] == "media" for event in s.pane.events)


def test_if_another_version_is_chosen_while_the_player_is_tried_the_answer_shows_nothing():
    media = FakeMedia(supported=None)
    s = Setup("/home/u/film.mp4", media=media)
    unpack_video(s)
    s.current = s.target("b")  # the choice changed while the other process was running
    before = list(s.pane.events)

    media.answer(True)

    assert s.pane.events == before


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


class Launcher:
    launched = []

    def __init__(self, gfile):
        self.gfile = gfile

    @classmethod
    def new(cls, gfile):
        return cls(gfile)

    def launch(self, window, cancellable, callback):
        Launcher.launched.append((self.gfile.get_path(), callback))


def test_opening_outside_hands_the_unpacked_file_to_its_own_application(monkeypatch):
    Launcher.launched = []
    monkeypatch.setattr(version_preview, "Gtk", SimpleNamespace(FileLauncher=Launcher))
    s = Setup()
    s.current = s.target("a")

    s.previewer.open_outside(s.current)
    s.finish("j1", message="/run/preview/a/photo.jpg")

    assert [path for path, _callback in Launcher.launched] == ["/run/preview/a/photo.jpg"]


def finished_with(error):
    def launch_finish(result):
        if error is not None:
            raise error

    return SimpleNamespace(launch_finish=launch_finish)


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
