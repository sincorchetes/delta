"""Opens the Delta app (its own .desktop entry; a running instance is just brought forward)."""

import logging

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

APP_DESKTOP_ID = "io.github.sincorchetes.Delta.desktop"
log = logging.getLogger(__name__)


def open_ui() -> None:
    log.info("opening the Delta app from a notification")
    info = Gio.DesktopAppInfo.new(APP_DESKTOP_ID)
    if info is None:
        log.warning("cannot open the Delta app: %s is not installed", APP_DESKTOP_ID)
        return
    try:
        info.launch([], None)
    except GLib.Error as err:
        log.warning("cannot open the Delta app: %s", err.message)
