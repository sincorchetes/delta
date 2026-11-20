"""Whether the player can be made is found out in another process, because GTK ends the whole program when it cannot.

Real processes stand in for the one that makes the player: one that ends well, one that is ended by a signal as GLib does
when GStreamer cannot find what it needs, and one that does not exist.
"""

import sys
import time

import pytest

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gio", "2.0")
    from gi.repository import GLib
except (ValueError, ImportError):
    pytest.skip("GLib is not available", allow_module_level=True)

from delta.ui import media_probe
from delta.ui.media_probe import MediaProbe

ENDS_WELL = [sys.executable, "-c", "pass"]
IS_ABORTED = [sys.executable, "-c", "import os; os.abort()"]  # what GLib does when GStreamer cannot make the player
EXITS_WITH_AN_ERROR = [sys.executable, "-c", "raise SystemExit(3)"]  # no display


def pump(until, seconds=10.0):
    """Run the main context until `until()` holds, as the window's own loop would."""
    context, deadline = GLib.MainContext.default(), time.monotonic() + seconds
    while not until() and time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.005)
    return until()


def answers(probe, times=1):
    found = []
    for _ in range(times):
        probe.check(found.append)
    return found


def test_a_process_that_ends_well_means_the_player_can_be_made():
    found = answers(MediaProbe(ENDS_WELL))

    assert pump(lambda: found) and found == [True]


@pytest.mark.parametrize("argv", [IS_ABORTED, EXITS_WITH_AN_ERROR], ids=["aborted", "error"])
def test_a_process_that_is_lost_or_fails_means_it_cannot(argv):
    found = answers(MediaProbe(argv))

    assert pump(lambda: found) and found == [False]


def test_when_the_process_cannot_even_be_started_the_answer_is_no_at_once():
    found = answers(MediaProbe(["/nonexistent/delta-probe"]))

    assert found == [False]


def test_the_answer_is_kept_and_no_other_process_is_started(tmp_path):
    runs = tmp_path / "runs"
    probe = MediaProbe([sys.executable, "-c", f"open({str(runs)!r}, 'a').write('x')"])
    first = answers(probe)
    assert pump(lambda: first)

    again = answers(probe, times=2)

    assert first == [True] and again == [True, True]  # the answer came without waiting for anything
    assert runs.read_text() == "x"


def test_those_who_ask_while_it_runs_get_the_one_answer_of_one_process(tmp_path):
    runs = tmp_path / "runs"
    probe = MediaProbe([sys.executable, "-c", f"open({str(runs)!r}, 'a').write('x')"])

    found = answers(probe, times=3)

    assert found == [] and pump(lambda: len(found) == 3)
    assert found == [True, True, True] and runs.read_text() == "x"


def test_by_default_it_is_a_python_that_makes_the_player_of_gtk():
    argv = MediaProbe()._argv

    assert argv[:2] == [sys.executable, "-c"]
    assert "Gtk.MediaFile.new_for_filename" in argv[2] and "Gtk.init_check()" in argv[2]
    assert isinstance(media_probe.SHARED, MediaProbe)
