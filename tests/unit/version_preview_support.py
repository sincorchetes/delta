"""What the tests of test_version_preview share."""

import pytest
from types import SimpleNamespace
from delta.ui.job_tracker import JobTracker
from delta.ui.version_preview import Target, VersionPreviewer


gi = pytest.importorskip("gi")


try:
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio
except (ValueError, ImportError):
    pytest.skip("GTK 4 is not available", allow_module_level=True)


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
            self.client,
            self.tracker,
            self.pane,
            None,
            lambda: self.current,
            lambda: self.changes.append(1),
            self.toasts.append,
            scratch_root=scratch_root,
            media=self.media,
        )

    def target(self, snapshot, size=1000, is_dir=False, path=None):
        return Target(snapshot, path or self.path, size, is_dir)

    def select(self, chosen):
        self.current = chosen
        self.previewer.show(chosen)

    def finish(self, job, ok=True, message="/run/preview/x"):
        self.tracker.on_started(job, None)
        self.tracker.on_finished(job, ok, message)


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


def unpack_video(s, name="film.mp4"):
    s.select(s.target("a"))
    s.finish("j1", message=f"/run/preview/a/{name}")


class Launcher:
    launched = []

    def __init__(self, gfile):
        self.gfile = gfile

    @classmethod
    def new(cls, gfile):
        return cls(gfile)

    def launch(self, window, cancellable, callback):
        Launcher.launched.append((self.gfile.get_path(), callback))


def finished_with(error):
    def launch_finish(result):
        if error is not None:
            raise error

    return SimpleNamespace(launch_finish=launch_finish)
