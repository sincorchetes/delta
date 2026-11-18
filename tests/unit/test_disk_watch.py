import time

import pytest

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gio", "2.0")
    from gi.repository import GLib
except (ValueError, ImportError):
    pytest.skip("GLib is not available", allow_module_level=True)

from delta.ui.disk_watch import DiskWatch

# PyGObject warns about asyncio's event-loop policy each time the main context is iterated.
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def pump(seconds, until=lambda: False):
    """Run the main context for a while, as the window's own loop would."""
    context, deadline = GLib.MainContext.default(), time.monotonic() + seconds
    while time.monotonic() < deadline and not until():
        context.iteration(False)
        time.sleep(0.005)


def test_something_deleted_in_the_folder_is_noticed(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    calls = []
    watch = DiskWatch(lambda: calls.append(1), delay_ms=50)
    watch.watch(str(tmp_path))

    (tmp_path / "a.txt").unlink()
    pump(3, until=lambda: calls)

    watch.stop()
    assert calls == [1]


def test_a_burst_of_changes_is_one_call(tmp_path):
    calls = []
    watch = DiskWatch(lambda: calls.append(1), delay_ms=150)
    watch.watch(str(tmp_path))

    for n in range(20):  # a restore writes several things in a row
        (tmp_path / f"f{n}.txt").write_text("x")
    pump(1.0)

    watch.stop()
    assert calls == [1]


def test_nothing_happening_means_no_call(tmp_path):
    calls = []
    watch = DiskWatch(lambda: calls.append(1), delay_ms=50)
    watch.watch(str(tmp_path))
    pump(0.4)
    watch.stop()
    assert calls == []


def test_after_stopping_nothing_is_reported(tmp_path):
    calls = []
    watch = DiskWatch(lambda: calls.append(1), delay_ms=50)
    watch.watch(str(tmp_path))
    watch.stop()

    (tmp_path / "late.txt").write_text("x")
    pump(0.4)

    assert calls == []


def test_changes_pending_when_it_is_stopped_are_dropped(tmp_path):
    calls = []
    watch = DiskWatch(lambda: calls.append(1), delay_ms=200)
    watch.watch(str(tmp_path))
    (tmp_path / "a.txt").write_text("x")
    pump(0.1)

    watch.stop()
    pump(0.5)

    assert calls == []


def test_following_another_folder_forgets_the_first(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    calls = []
    watch = DiskWatch(lambda: calls.append(1), delay_ms=50)
    watch.watch(str(first))
    watch.watch(str(second))

    (first / "ignored.txt").write_text("x")
    pump(0.4)
    assert calls == []

    (second / "seen.txt").write_text("x")
    pump(3, until=lambda: calls)
    watch.stop()
    assert calls == [1]


def test_a_folder_that_does_not_exist_is_not_an_error(tmp_path):
    watch = DiskWatch(lambda: None)
    watch.watch(str(tmp_path / "gone"))
    watch.stop()
