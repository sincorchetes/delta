"""The area of the version window that shows one version: an image, some text, or a message."""

import logging
import os
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from delta.i18n import _
from delta.ui.a11y import loading_spinner
from delta.ui.preview_kind import TEXT_SHOWN_BYTES, looks_binary

log = logging.getLogger(__name__)


def read_text_head(path: str) -> str | None:
    """The first part of a text file, or None when it is unreadable or really binary."""
    try:
        with open(path, "rb") as handle:
            chunk = handle.read(TEXT_SHOWN_BYTES)
    except OSError:
        return None
    return None if looks_binary(chunk) else chunk.decode("utf-8", errors="replace")


class PreviewPane(Gtk.Stack):
    def __init__(self) -> None:
        super().__init__(hexpand=True, vexpand=True)
        self._picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self._text = Gtk.TextView(
            editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR,
            left_margin=12, right_margin=12, top_margin=12, bottom_margin=12,
        )
        self._video = Gtk.Video(autoplay=False, loop=False)  # its controls play, seek and set the volume
        self._media: Gtk.MediaFile | None = None
        self._status = Adw.StatusPage()
        self.add_named(loading_spinner(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER), "loading")
        self.add_named(self._picture, "image")
        self.add_named(self._video, "media")
        self.add_named(Gtk.ScrolledWindow(child=self._text), "text")
        self.add_named(self._status, "status")
        self.show_message("", "")

    def show_loading(self) -> None:
        self.stop_media()
        self.set_visible_child_name("loading")

    def stop_media(self) -> None:
        """Silence the player before anything else is shown (or the window closes).

        The stream stays attached to the video until another replaces it: detaching it with
        `set_media_stream(None)` makes GTK release it once too often (a GLib warning, with GStreamer).
        """
        if self._media is not None:
            self._media.pause()
            self._media = None

    def show_media(self, path: str, on_error: Callable[[], None]) -> None:
        """A video or audio file, paused, with the player's own controls.

        GStreamer reports a missing codec after the page is up, so `on_error` runs later.
        """
        self.stop_media()
        media = Gtk.MediaFile.new_for_filename(path)
        media.connect("notify::error", lambda stream, pspec: self._media_error(stream, path, on_error))
        self._media = media
        self._video.set_media_stream(media)
        self.set_visible_child_name("media")
        self._media_error(media, path, on_error)

    @staticmethod
    def _media_error(stream: Gtk.MediaFile, path: str, on_error: Callable[[], None]) -> None:
        error = stream.get_error()
        if error is not None:
            log.warning("the player cannot play %s: %s", os.path.basename(path), error.message)
            on_error()

    def show_message(self, title: str, detail: str, icon: str = "document-open-recent-symbolic") -> None:
        self.stop_media()
        self._status.set_icon_name(icon)
        self._status.set_title(GLib.markup_escape_text(title))
        self._status.set_description(GLib.markup_escape_text(detail))
        self._status.set_child(None)
        self.set_visible_child_name("status")

    def show_action(self, title: str, detail: str, label: str, callback: Callable[[], None], icon: str = "document-open-symbolic") -> None:
        """A message with one button, for what cannot (or should not yet) be shown here."""
        self.show_message(title, detail, icon)
        button = Gtk.Button(label=label, halign=Gtk.Align.CENTER)
        button.add_css_class("pill")
        button.add_css_class("suggested-action")
        button.connect("clicked", lambda b: callback())
        self._status.set_child(button)

    def show_image(self, path: str) -> bool:
        """False when no loader understands the file (the caller falls back to its own app)."""
        self.stop_media()
        try:
            self._picture.set_paintable(Gdk.Texture.new_from_filename(path))
        except GLib.Error:
            return False
        self._picture.set_alternative_text(_("Preview of {name}").format(name=os.path.basename(path)))
        self.set_visible_child_name("image")
        return True

    def show_text(self, path: str) -> bool:
        self.stop_media()
        head = read_text_head(path)
        if head is None:
            return False
        self._text.get_buffer().set_text(head)
        self.set_visible_child_name("text")
        return True
