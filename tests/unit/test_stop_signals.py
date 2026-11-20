"""The stop signals reach the daemon through the real GLib, whichever release the system has.

The unit test of the startup uses a stand-in for this; a daemon that called `GLibUnix.signal_add`, which only the newest GLib has,
passed that and died at startup on Fedora 43, Debian 13 and Enterprise Linux 10. Here nothing is replaced.
"""

import os
import signal
import time

from gi.repository import GLib

from delta.daemon.stop_signals import watch_signal


def until(condition, timeout=5.0):
    context, deadline = GLib.MainContext.default(), time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)
    return condition()


def test_a_signal_is_handled_by_the_main_loop_with_the_real_glib():
    seen = []
    watch_signal(signal.SIGUSR1, lambda: seen.append("handled") or GLib.SOURCE_REMOVE)

    os.kill(os.getpid(), signal.SIGUSR1)

    assert until(lambda: seen) and seen == ["handled"]


def test_a_handler_that_asks_to_stay_hears_the_next_signal_too():
    seen = []
    watch_signal(signal.SIGUSR2, lambda: seen.append("heard") or (GLib.SOURCE_CONTINUE if len(seen) < 2 else GLib.SOURCE_REMOVE))

    os.kill(os.getpid(), signal.SIGUSR2)
    assert until(lambda: len(seen) == 1)
    os.kill(os.getpid(), signal.SIGUSR2)

    assert until(lambda: len(seen) == 2) and seen == ["heard", "heard"]
