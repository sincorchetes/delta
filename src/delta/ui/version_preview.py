"""Shows one thing from a backup inside the window, unpacking it first when that is needed."""

import logging
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk

from delta.i18n import _
from delta.ui.client import DeltaClient
from delta.ui.id3 import copy_without_id3v2
from delta.ui.job_tracker import JobTracker
from delta.ui.media_probe import SHARED, MediaProbe
from delta.ui.preview_kind import Kind, icon_for, kind_of, needs_confirmation, needs_untagged_copy
from delta.ui.preview_pane import PreviewPane
from delta.ui.status import summarise
from delta.ui.versions import format_size

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Target:
    """A path as it was in one snapshot: the opened item itself, or a file inside a folder."""

    snapshot: str
    path: str
    size: int
    is_dir: bool = False


class VersionPreviewer:
    """One job runs at a time, so a target picked meanwhile waits and is shown when it ends."""

    def __init__(
        self,
        client: DeltaClient,
        tracker: JobTracker,
        pane: PreviewPane,
        window: Gtk.Window,
        current: Callable[[], Target | None],
        on_change: Callable[[], None],
        toast: Callable[[str], None],
        scratch_root: str | None = None,
        media: MediaProbe | None = None,
    ) -> None:
        self._client, self._tracker = client, tracker
        self._pane, self._window = pane, window
        self._current, self._on_change, self._toast = current, on_change, toast
        self._scratch_root = scratch_root
        self._media = media or SHARED
        self._scratch: str | None = None  # copies made for the player; removed on close()
        self._unpacked: dict[tuple[str, str], str] = {}  # (snapshot, path) -> where it was unpacked
        self._confirmed: set[tuple[str, str]] = set()  # big ones the user agreed to unpack
        self._pending: Target | None = None

    def show(self, target: Target) -> None:
        """Put `target` in the pane: at once if it is cheap, after asking if it is big."""
        kind = self._kind(target)
        if kind is Kind.FOLDER:
            self._pane.show_action(
                os.path.basename(target.path), _("A folder: open this version to browse what it held."),
                _("Open"), lambda: self.open_outside(target), "folder-symbolic",
            )
        elif kind is Kind.OTHER:
            self._offer_to_open(target)
        elif needs_confirmation(kind, target.size) and self._key(target) not in self._confirmed:
            self._pane.show_action(
                _("Large file"),
                _("This version is {size}. It has to be unpacked before it can be shown.").format(size=format_size(target.size)),
                _("Show preview"), lambda: self._confirm(target), icon_for(self._mime(target)),
            )
        else:
            self._unpack(target, outside=False)

    def open_outside(self, target: Target) -> None:
        """Open it with its own application (a folder opens in Files)."""
        self._unpack(target, outside=True)

    def drain(self) -> None:
        """Call whenever the tracker frees up: show the target picked while it was busy."""
        pending, self._pending = self._pending, None
        if pending is not None and not self._tracker.busy and self._current() == pending:
            self.show(pending)

    def close(self) -> None:
        """Remove the copies made for the player."""
        if self._scratch is not None:
            shutil.rmtree(self._scratch, ignore_errors=True)
            self._scratch = None

    @staticmethod
    def _key(target: Target) -> tuple[str, str]:
        return target.snapshot, target.path

    def _confirm(self, target: Target) -> None:
        self._confirmed.add(self._key(target))
        self.show(target)

    @staticmethod
    def _mime(target: Target) -> str:
        return Gio.content_type_guess(os.path.basename(target.path), None)[0] or ""

    def _kind(self, target: Target) -> Kind:
        return kind_of(self._mime(target), target.is_dir)

    def _offer_to_open(self, target: Target) -> None:
        self._pane.show_action(
            os.path.basename(target.path), _("This kind of file opens in its own application."), _("Open"),
            lambda: self.open_outside(target), icon_for(self._mime(target)),
        )

    def _unpack(self, target: Target, outside: bool) -> None:
        known = self._unpacked.get(self._key(target))
        if known is not None:
            self._arrived(target, known, outside)
        elif self._tracker.busy:
            self._pending = target
        else:
            self._pane.show_loading()
            self._tracker.begin(lambda ok, message: self._unpacked_done(target, outside, ok, message))
            self._on_change()
            self._client.preview_version(target.snapshot, target.path, self._tracker.on_started)

    def _unpacked_done(self, target: Target, outside: bool, ok: bool, message: str) -> None:
        if ok:
            self._unpacked[self._key(target)] = message
        self._on_change()
        if not ok:
            self._failed(target, outside, message)
        else:
            self._arrived(target, message, outside)
        self.drain()

    def _failed(self, target: Target, outside: bool, message: str) -> None:
        detail = summarise(message) or _("It could not be opened.")
        if outside:
            self._toast(detail)
        elif self._current() == target:
            self._pane.show_message(_("Could not show this version"), detail, "dialog-error-symbolic")

    def _arrived(self, target: Target, path: str, outside: bool) -> None:
        if outside:
            Gtk.FileLauncher.new(Gio.File.new_for_path(path)).launch(self._window, None, self._launched)
        elif self._current() == target:
            self._render(target, path)

    def _render(self, target: Target, path: str) -> None:
        kind = self._kind(target)
        if kind is Kind.IMAGE and self._pane.show_image(path):
            return
        if kind is Kind.TEXT and self._pane.show_text(path):
            return
        if kind in (Kind.VIDEO, Kind.AUDIO):
            self._media.check(lambda supported: self._play(target, path, supported))
            return
        self._offer_to_open(target)

    def _play(self, target: Target, path: str, supported: bool) -> None:
        """Called when it is known whether the player can be made here; without it the file goes to its own application."""
        if self._current() != target:
            return  # another version was chosen while that was being found out
        playable = self._playable(target, path) if supported else None
        if playable is None:
            self._offer_to_open(target)
        else:
            self._pane.show_media(playable, lambda: self._media_failed(target))

    def _playable(self, target: Target, path: str) -> str | None:
        """What to hand the player: the file itself, or for an mp3 a copy without its ID3 tag.

        None when that copy cannot be made, so the file is offered to its own application instead
        of risking the player on the original.
        """
        if not needs_untagged_copy(self._mime(target)):
            return path
        try:
            if self._scratch is None:
                self._scratch = tempfile.mkdtemp(prefix="delta-audio-", dir=self._scratch_root or GLib.get_user_runtime_dir())
            descriptor, copy = tempfile.mkstemp(suffix=".mp3", dir=self._scratch)
            os.close(descriptor)
            if copy_without_id3v2(path, copy):
                return copy
            os.unlink(copy)  # it had no tag: nothing to take off
            return path
        except OSError:
            return None

    def _media_failed(self, target: Target) -> None:
        """No codec for it here: its own application may have one."""
        if self._current() == target:
            self._offer_to_open(target)

    def _launched(self, launcher, result) -> None:
        try:
            launcher.launch_finish(result)
        except GLib.Error as err:
            if not err.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                log.warning("cannot open the version with another application: %s", err.message)
                self._toast(_("No application could open this version."))
