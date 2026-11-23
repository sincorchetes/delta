"""What the controller of an open snapshot tells, remembers and gives back: the rules, with GLib, Gio and the bus replaced."""

import logging
from types import SimpleNamespace

import pytest
from gi.repository import Gio, GLib

from delta.daemon import browse_controller
from delta.daemon.browse_controller import (
    CHECK_SECONDS,
    REASON_REQUESTED,
    REASON_UNUSED,
    UNUSED_GRACE_SECONDS,
    BrowseController,
)
from delta.daemon.job_calls import ERROR_UNAVAILABLE

PATH, INTERFACE = "/io/github/sincorchetes/Delta/Service1", "io.github.sincorchetes.Delta.Service1"


class Wire:
    def __init__(self):
        self.sent = []

    def emit_signal(self, destination, path, interface, signal, parameters):
        self.sent.append((destination, path, interface, signal, parameters.unpack()))


class Jobs:
    def __init__(self):
        self.backup_running = False
        self.results, self.idle = [], []

    def submit_when_idle(self, job_id, task):
        self.results.append(task(None))

    def when_idle(self, callback):
        self.idle.append(callback)
        callback()


class Opened:
    mountpoint = "/run/browse/snapshot"

    def __init__(self):
        self.closed = 0

    def close(self):
        self.closed += 1


class Invocation:
    def __init__(self):
        self.value = self.error = None

    def return_value(self, value):
        self.value = value.unpack()

    def return_dbus_error(self, name, message):
        self.error = (name, message)


@pytest.fixture
def calls(monkeypatch):
    seen = SimpleNamespace(idle=[], timers=[], removed=[], watched=[], unwatched=[])
    monkeypatch.setattr(
        browse_controller,
        "GLib",
        SimpleNamespace(
            idle_add=lambda function, *args: seen.idle.append((function, args)) or 1,
            timeout_add_seconds=lambda seconds, function: seen.timers.append((seconds, function)) or 7,
            source_remove=seen.removed.append,
            Variant=GLib.Variant,
            SOURCE_REMOVE=GLib.SOURCE_REMOVE,
            SOURCE_CONTINUE=GLib.SOURCE_CONTINUE,
        ),
    )
    monkeypatch.setattr(
        browse_controller,
        "Gio",
        SimpleNamespace(
            bus_watch_name_on_connection=lambda *args: seen.watched.append(args) or 5,
            bus_unwatch_name=seen.unwatched.append,
            BusNameWatcherFlags=Gio.BusNameWatcherFlags,
            DBusConnection=Gio.DBusConnection,
        ),
    )
    return seen


def make(calls, **fields):
    wire, jobs, resumed = Wire(), Jobs(), []
    controller = BrowseController(wire, jobs, lambda: None, resumed.append, **fields)
    return controller, wire, jobs, resumed


def test_a_new_controller_has_nothing_open_nothing_pending_nothing_owed_and_nothing_watched(calls):
    controller, *_rest = make(calls)

    assert controller.is_open is False
    assert controller._unused_since is None and controller._last_users is None
    assert controller._timer == 0 and controller._watch_id == 0
    assert controller._pending is False and controller._owed is False


def test_a_backup_that_has_to_wait_is_told_once_and_not_at_every_attempt(calls):
    told = []
    controller, *_rest = make(calls, on_postponed=lambda: told.append("postponed"))
    controller._open = Opened()

    assert controller.postpone() is True
    assert told == ["postponed"]  # at the first attempt, not at a later one
    assert controller._owed is True

    assert controller.postpone() is True
    assert told == ["postponed"]  # and not again


def test_with_nothing_open_or_being_opened_a_backup_does_not_wait(calls):
    told = []
    controller, *_rest = make(calls, on_postponed=lambda: told.append("postponed"))

    assert controller.postpone() is False and told == [] and controller._owed is False


def test_browsing_that_is_not_available_says_so_with_its_error(calls):
    controller, *_rest = make(calls)
    invocation = Invocation()

    controller.mount(None, SimpleNamespace(unpack=lambda: ("s",)), ":1.5", invocation)

    assert invocation.error == (ERROR_UNAVAILABLE, "browsing backups is not available")


def test_an_opening_that_works_leaves_nothing_pending_and_returns_the_folder(calls):
    controller, _wire, jobs, resumed = make(calls)
    invocation = Invocation()

    class Browse(Opened):
        def open(self, snapshot):
            return "/run/browse/" + snapshot

    controller.mount(Browse(), SimpleNamespace(unpack=lambda: ("snap-1",)), ":1.5", invocation)

    assert jobs.results == [(True, "/run/browse/snap-1")] and invocation.value is not None
    assert controller._pending is False and controller.is_open
    assert resumed == []  # nothing was turned away, and nothing needs to be started


def test_an_opening_that_fails_leaves_nothing_pending_gives_the_repository_back_and_says_it_failed(calls):
    controller, _wire, jobs, resumed = make(calls)
    controller._owed = True

    class Failing(Opened):
        def open(self, snapshot):
            raise RuntimeError("cannot mount")

    with pytest.raises(RuntimeError, match="cannot mount"):
        controller.mount(Failing(), SimpleNamespace(unpack=lambda: ("snap-1",)), ":1.5", Invocation())

    assert controller._pending is False and not controller.is_open
    assert resumed == [True] and controller._owed is False  # the backup that was turned away starts now


def test_a_backup_that_runs_is_interrupted_before_opening(calls):
    controller, _wire, jobs, _resumed = make(calls)
    stopped = []
    controller._interrupt = lambda: stopped.append("interrupted")
    jobs.backup_running = True

    class Browse(Opened):
        def open(self, snapshot):
            return "/x"

    controller.mount(Browse(), SimpleNamespace(unpack=lambda: ("snap",)), ":1.5", Invocation())

    assert stopped == ["interrupted"]


def test_closing_tells_the_windows_with_the_reason_ends_the_job_well_and_logs_why(calls, caplog):
    controller, wire, jobs, resumed = make(calls)
    opened = Opened()
    controller._open = opened
    controller._owed = True

    with caplog.at_level(logging.INFO, logger="delta.daemon.browse_controller"):
        job_id = controller.close(REASON_REQUESTED)

    assert job_id and jobs.results == [(True, "")]
    assert wire.sent == [(None, PATH, INTERFACE, "SnapshotClosed", (REASON_REQUESTED,))]
    assert opened.closed == 1 and not controller.is_open
    assert resumed == [True] and controller._owed is False  # what was turned away starts, and is not owed any more
    assert "closing the open snapshot: requested" in [record.getMessage() for record in caplog.records]


def test_closing_what_is_not_open_does_nothing(calls):
    controller, wire, jobs, _resumed = make(calls)

    assert controller.close(REASON_REQUESTED) is None and wire.sent == [] and jobs.results == []


def test_the_owner_of_the_folder_is_watched_by_its_name_and_its_disappearance_is_followed(calls):
    controller, wire, *_rest = make(calls, usage=SimpleNamespace(users=lambda mountpoint: []))

    result = controller._watch(":1.9")

    assert calls.watched == [(wire, ":1.9", Gio.BusNameWatcherFlags.NONE, None, controller._on_vanished)]
    assert controller._watch_id == 5 and controller._timer == 7
    assert calls.timers == [(CHECK_SECONDS, controller._check_usage)]
    assert controller._unused_since is None and controller._last_users is None
    assert result is GLib.SOURCE_REMOVE


def test_what_was_watched_is_let_go_and_forgotten(calls):
    controller, *_rest = make(calls)
    controller._watch_id, controller._timer = 5, 7

    assert controller._unwatch() is GLib.SOURCE_REMOVE

    assert calls.unwatched == [5] and calls.removed == [7]
    assert controller._watch_id == 0 and controller._timer == 0


def test_nothing_is_let_go_when_nothing_was_watched(calls):
    controller, *_rest = make(calls)

    controller._unwatch()

    assert calls.unwatched == [] and calls.removed == []


def test_who_uses_the_folder_is_logged_when_it_changes_and_not_at_every_look(calls, caplog):
    controller, *_rest = make(calls, usage=SimpleNamespace(users=lambda mountpoint: ["evince (4): has a file open", "files (5): watches a folder"]))
    controller._open = Opened()

    with caplog.at_level(logging.INFO, logger="delta.daemon.browse_controller"):
        assert controller._check_usage() is GLib.SOURCE_CONTINUE
        assert controller._check_usage() is GLib.SOURCE_CONTINUE

    assert [record.getMessage() for record in caplog.records] == [
        "the open snapshot is used by: evince (4): has a file open; files (5): watches a folder"
    ]
    assert controller._unused_since is None


def test_a_folder_that_nobody_uses_for_the_grace_time_is_closed_and_its_timer_forgotten(calls, caplog):
    clock = SimpleNamespace(now=1000.0)
    controller, wire, _jobs, _resumed = make(calls, usage=SimpleNamespace(users=lambda mountpoint: []), clock=lambda: clock.now)
    controller._open = Opened()
    controller._timer = 7

    with caplog.at_level(logging.INFO, logger="delta.daemon.browse_controller"):
        assert controller._check_usage() is GLib.SOURCE_CONTINUE  # first look: nobody, since now
        clock.now += UNUSED_GRACE_SECONDS - 1
        assert controller._check_usage() is GLib.SOURCE_CONTINUE  # almost
        clock.now += 1
        assert controller._check_usage() is GLib.SOURCE_REMOVE  # exactly the grace time: closed

    assert controller._timer == 0 and not controller.is_open
    assert wire.sent == [(None, PATH, INTERFACE, "SnapshotClosed", (REASON_UNUSED,))]
    assert "the open snapshot is used by: nobody" in [record.getMessage() for record in caplog.records]


def test_nothing_is_looked_at_when_nothing_is_open_or_there_is_no_way_to_look(calls):
    closed, no_usage = make(calls, usage=SimpleNamespace(users=lambda mountpoint: []))[0], make(calls)[0]
    no_usage._open = Opened()

    assert closed._check_usage() is GLib.SOURCE_REMOVE
    assert no_usage._check_usage() is GLib.SOURCE_REMOVE


def test_an_owner_that_vanishes_closes_the_snapshot_and_it_is_said_which(calls, caplog):
    controller, wire, *_rest = make(calls)
    controller._open = Opened()

    with caplog.at_level(logging.INFO, logger="delta.daemon.browse_controller"):
        controller._on_vanished(None, ":1.42")

    assert "\n".join(record.getMessage() for record in caplog.records).startswith(
        ":1.42 went away with a snapshot open; closing it"
    )
    assert wire.sent[0][3:] == ("SnapshotClosed", ("owner-gone",))
