"""Unix signals, watched through the main loop."""

from collections.abc import Callable

import gi

gi.require_version("GLibUnix", "2.0")
from gi.repository import GLibUnix


def watch_signal(signum: int, handler: Callable[[], bool]) -> None:
    """Call `handler` from the main loop when `signum` arrives; it returns whether to keep watching.

    `GLibUnix.signal_add` only exists in the newest GLib (a daemon that called it died at startup on Fedora 43, Debian 13
    and Enterprise Linux 10): a source is made and attached instead, which every GLib that has GLibUnix at all can do.
    """
    source = GLibUnix.signal_source_new(signum)
    source.set_callback(lambda *_arguments: handler())
    source.attach(None)
