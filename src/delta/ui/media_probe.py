"""Whether this system can make GTK's player, found out in a process of its own.

GTK plays a video or an audio through GStreamer, and when GStreamer cannot find what it needs (the plugin that plays, a
GL library) GLib ends the whole process with an error that Python cannot catch: the window would close under whoever asked
for a preview. So the player is first made in a process that can be lost, once, and the answer is kept.
"""

import logging
import sys
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

log = logging.getLogger(__name__)

# What the other process does: it makes the player, which is where GTK ends the process if it cannot. Having no display
# is a refusal too, since then nothing can be shown.
PROBE = """
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
if not Gtk.init_check():
    raise SystemExit(3)
Gtk.MediaFile.new_for_filename("/nonexistent")
"""


class MediaProbe:
    def __init__(self, argv: list[str] | None = None) -> None:
        self._argv = argv or [sys.executable, "-c", PROBE]
        self._supported: bool | None = None
        self._waiting: list[Callable[[bool], None]] = []
        self._started = False

    def check(self, then: Callable[[bool], None]) -> None:
        """Calls `then(True)` when the player can be made, `then(False)` when it cannot. At once if it is already known."""
        if self._supported is not None:
            then(self._supported)
            return
        self._waiting.append(then)
        if not self._started:
            self._start()

    def _start(self) -> None:
        self._started = True
        try:
            process = Gio.Subprocess.new(self._argv, Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE)
        except GLib.Error as err:
            log.warning("cannot try the player: %s", err.message)
            self._answer(False)
            return
        process.wait_check_async(None, self._done)

    def _done(self, process: Gio.Subprocess, result: Gio.AsyncResult) -> None:
        try:
            process.wait_check_finish(result)
        except GLib.Error as err:
            log.warning("this system cannot play a video or an audio, so they are offered to their own application: %s", err.message)
            self._answer(False)
        else:
            self._answer(True)

    def _answer(self, supported: bool) -> None:
        self._supported = supported
        waiting, self._waiting = self._waiting, []
        for then in waiting:
            then(supported)


SHARED = MediaProbe()  # one answer for the whole process: the system does not change while it runs
