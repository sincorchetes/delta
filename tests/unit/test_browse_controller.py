"""Opening a snapshot wins over backing up, with the jobs, the bus and the mount replaced by stand-ins."""

from types import SimpleNamespace

import pytest
from gi.repository import GLib

from delta.daemon import browse_controller
from delta.daemon.browse_controller import BrowseController
from delta.domain.errors import DeltaError, EngineError


class Jobs:
    """Runs a job when told to (or at once), on the caller's thread."""

    def __init__(self):
        self.backup_running = False
        self.hold = False
        self.waiting = []
        self.ran = []
        self.idle = []

    def submit_when_idle(self, job_id, task):
        self.waiting.append((job_id, task))
        if not self.hold:
            self.run_waiting()

    def run_waiting(self):
        while self.waiting:
            job_id, task = self.waiting.pop(0)
            self.ran.append((job_id, task(None)))

    def when_idle(self, callback):
        self.idle.append(callback)
        callback()


class Browse:
    def __init__(self, path="/run/browse/snapshot", fail=None, close_fails=False):
        self.path, self.mountpoint, self.fail, self.close_fails = path, path, fail, close_fails
        self.opened, self.closed, self.is_open = [], 0, False

    def open(self, snapshot):
        if self.fail:
            raise self.fail
        self.opened.append(snapshot)
        self.is_open = True
        return self.path

    def close(self):
        ORDER.append("unmount")
        self.closed += 1
        self.is_open = False
        if self.close_fails:
            raise EngineError("could not be closed")


class Invocation:
    def __init__(self):
        self.value = self.error = None

    def return_value(self, value):
        self.value = value.unpack()

    def return_dbus_error(self, name, message):
        self.error = (name, message)


class Connection:
    def __init__(self):
        self.signals = []

    def emit_signal(self, bus_name, path, interface, signal, parameters):
        self.signals.append((signal, parameters.unpack()))


ORDER = []  # what happened, in order: "hold", "unmount", "release"


class Events:
    def watch(self, callback):
        self.callback = callback

    def hold(self):
        ORDER.append("hold")

    def release(self):
        ORDER.append("release")


class Usage:
    def __init__(self):
        self.busy, self.asked = False, []

    def users(self, mountpoint):
        self.asked.append(mountpoint)
        return ["evince (7): has a file or folder open"] if self.busy else []


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def world(monkeypatch):
    ORDER.clear()
    watches = SimpleNamespace(added=[], removed=[])

    def watch_name(connection, name, flags, appeared, vanished):
        watches.added.append((name, vanished))
        return len(watches.added)

    monkeypatch.setattr(
        browse_controller,
        "Gio",
        SimpleNamespace(
            BusNameWatcherFlags=SimpleNamespace(NONE=0),
            bus_watch_name_on_connection=watch_name,
            bus_unwatch_name=watches.removed.append,
        ),
    )
    timers = SimpleNamespace(added=[], removed=[])

    def start_timer(seconds, func):
        timers.added.append((seconds, func))
        return len(timers.added)

    monkeypatch.setattr(
        browse_controller,
        "GLib",
        SimpleNamespace(
            idle_add=lambda func, *args: func(*args),
            Variant=GLib.Variant,
            SOURCE_REMOVE=False,
            SOURCE_CONTINUE=True,
            timeout_add_seconds=start_timer,
            source_remove=timers.removed.append,
        ),
    )
    jobs, connection, events, usage, clock = Jobs(), Connection(), Events(), Usage(), Clock()
    stops, resumes = [], []
    told = []
    controller = BrowseController(
        connection, jobs, lambda: stops.append(1), lambda owed: resumes.append(owed), events,
        on_postponed=lambda: told.append(1), usage=usage, clock=clock,
    )
    return SimpleNamespace(
        controller=controller, jobs=jobs, connection=connection, events=events,
        stops=stops, resumes=resumes, watches=watches, told=told, timers=timers, usage=usage, clock=clock,
    )


def mount(world, browse, snapshot="abc", sender=":1.42"):
    invocation = Invocation()
    world.controller.mount(browse, GLib.Variant("(s)", (snapshot,)), sender, invocation)
    return invocation


def test_without_a_mounter_browsing_is_unavailable(world):
    invocation = mount(world, None)

    assert "Unavailable" in invocation.error[0] and world.jobs.ran == []


def test_opening_answers_with_the_job_and_the_job_ends_with_the_folder(world):
    browse = Browse()

    invocation = mount(world, browse)

    job_id, outcome = world.jobs.ran[0]
    assert invocation.value == (job_id,)
    assert outcome == (True, "/run/browse/snapshot") and browse.opened == ["abc"]
    assert world.stops == []  # no backup was running


def test_opening_while_a_backup_runs_stops_it_first(world):
    world.jobs.backup_running = True

    mount(world, Browse())

    assert world.stops == [1]


def test_the_window_that_asked_is_watched_so_closing_it_closes_the_snapshot(world):
    browse = Browse()
    mount(world, browse)
    name, vanished = world.watches.added[0]

    vanished(None, name)

    assert name == ":1.42" and browse.closed == 1
    assert world.connection.signals == [("SnapshotClosed", ("owner-gone",))]
    assert world.watches.removed == [1]
    assert world.resumes == [False]


def test_opening_another_snapshot_closes_the_first_and_watches_the_new_window(world):
    first, second = Browse(), Browse("/run/browse/other")
    mount(world, first)

    mount(world, second, "def", sender=":1.43")

    assert first.closed == 1 and second.opened == ["def"]
    assert [name for name, _ in world.watches.added] == [":1.42", ":1.43"]
    assert world.watches.removed == [1]  # the first window is no longer watched


def test_an_opening_that_fails_gives_the_repository_back_and_resumes_the_backup(world):
    with pytest.raises(DeltaError):
        mount(world, Browse(fail=DeltaError("pruned since")))

    assert world.resumes == [False]
    assert world.controller.postpone() is False  # nothing is open or pending any more


def test_a_scheduled_backup_waits_while_opening_and_while_open_and_runs_after_closing(world):
    world.jobs.hold = True
    browse = Browse()
    assert world.controller.postpone() is False

    mount(world, browse)
    assert world.controller.postpone() is True  # being opened
    world.jobs.run_waiting()
    assert world.controller.postpone() is True  # open

    world.controller.close("requested")
    world.jobs.run_waiting()

    assert world.resumes == [True]  # the one that was turned away
    assert world.controller.postpone() is False


def check(world):
    """One tick of the timer that looks at whether the open folder is still used."""
    return world.timers.added[-1][1]()


def test_an_open_folder_is_checked_every_half_minute(world):
    mount(world, Browse())

    assert [seconds for seconds, _ in world.timers.added] == [30]
    assert check(world) is True and world.usage.asked == ["/run/browse/snapshot"]


def test_a_folder_nobody_uses_is_closed_after_a_while_and_the_backup_goes_on(world):
    browse = Browse()
    mount(world, browse)

    assert check(world) is True  # first time seen unused
    world.clock.now += 119
    assert check(world) is True and browse.closed == 0
    world.clock.now += 1
    assert check(world) is False

    assert browse.closed == 1 and world.resumes == [False]
    assert world.connection.signals == [("SnapshotClosed", ("unused",))]
    assert world.timers.removed == []  # the source ends by itself: it is not removed a second time


def test_who_uses_the_folder_is_logged_only_when_it_changes(world, caplog):
    mount(world, Browse())

    with caplog.at_level("INFO", logger=browse_controller.log.name):
        check(world)
        check(world)
        world.usage.busy = True
        check(world)
        check(world)

    lines = [r.getMessage() for r in caplog.records if "used by" in r.getMessage()]
    assert lines == [
        "the open snapshot is used by: nobody",
        "the open snapshot is used by: evince (7): has a file or folder open",
    ]


def test_use_starts_the_wait_over(world):
    browse = Browse()
    mount(world, browse)
    check(world)
    world.clock.now += 100

    world.usage.busy = True
    check(world)
    world.usage.busy = False
    world.clock.now += 100
    check(world)
    world.clock.now += 100
    assert check(world) is True  # only 100 s since it was last used

    assert browse.closed == 0


def test_closing_by_other_means_stops_the_check(world):
    mount(world, Browse())

    world.controller.close("requested")

    assert world.timers.removed == [1]


def test_a_check_after_the_folder_is_gone_ends_itself(world):
    mount(world, Browse())
    timer = world.timers.added[-1][1]
    world.controller.close("requested")

    assert timer() is False and world.usage.asked == []


def test_opening_another_snapshot_replaces_the_check(world):
    mount(world, Browse())

    mount(world, Browse("/run/browse/other"), sender=":1.43")

    assert world.timers.removed == [1] and len(world.timers.added) == 2


def test_without_a_way_to_see_use_the_folder_is_never_closed_by_idleness(world):
    controller = BrowseController(world.connection, world.jobs, lambda: None, lambda owed: None)
    controller.mount(Browse(), GLib.Variant("(s)", ("abc",)), ":1.42", Invocation())

    assert controller.is_open and world.timers.added == []
    assert controller._check_usage() is False


def test_the_user_is_told_once_that_a_backup_was_postponed_not_at_every_attempt(world):
    mount(world, Browse())

    world.controller.postpone()
    world.controller.postpone()
    assert world.told == [1]

    world.controller.close("requested")
    world.controller.postpone()  # nothing is open any more: nothing to tell
    assert world.told == [1]


def test_postponing_without_anyone_to_tell_is_fine(world):
    controller = BrowseController(world.connection, world.jobs, lambda: None, lambda owed: None)
    controller._open = object()

    assert controller.postpone() is True


def test_it_says_whether_a_snapshot_is_open(world):
    assert world.controller.is_open is False

    mount(world, Browse())

    assert world.controller.is_open is True


def test_every_closing_leaves_its_reason_in_the_log(world, caplog):
    mount(world, Browse())

    with caplog.at_level("INFO", logger=browse_controller.log.name):
        world.controller.close("unused")

    assert "closing the open snapshot: unused" in caplog.text


def test_closing_by_request_answers_with_its_job(world):
    mount(world, Browse())
    invocation = Invocation()

    world.controller.unmount(invocation)

    assert invocation.value == (world.jobs.ran[-1][0],)
    assert world.connection.signals == [("SnapshotClosed", ("requested",))]


def test_closing_when_nothing_is_open_answers_with_no_job(world):
    invocation = Invocation()

    world.controller.unmount(invocation)

    assert invocation.value == ("",) and world.connection.signals == []


def test_going_to_sleep_or_locking_closes_the_snapshot(world):
    browse = Browse()
    mount(world, browse)

    world.events.callback()

    assert browse.closed == 1
    assert world.connection.signals == [("SnapshotClosed", ("sleep-or-lock",))]


def test_without_session_events_nothing_is_watched():
    BrowseController(Connection(), Jobs(), lambda: None, lambda owed: None)


def test_shutting_down_closes_without_starting_a_backup(world):
    browse = Browse()
    mount(world, browse)

    world.controller.close("shutdown", resume=False)

    assert browse.closed == 1 and world.resumes == []


def test_sleeping_waits_while_a_snapshot_is_open_and_goes_on_once_it_is_closed(world):
    mount(world, Browse())
    assert ORDER[-1] == "hold"

    world.events.callback()

    assert ORDER[-3:] == ["hold", "unmount", "release"]  # the computer may sleep only after unmounting


def test_a_snapshot_that_will_not_unmount_still_lets_the_computer_sleep(world):
    mount(world, Browse(close_fails=True))

    with pytest.raises(EngineError):
        world.controller.close("requested")

    assert ORDER[-2:] == ["unmount", "release"]


def test_a_snapshot_that_cannot_be_closed_still_gives_the_repository_back(world):
    mount(world, Browse(close_fails=True))

    with pytest.raises(EngineError):
        world.controller.close("requested")

    assert world.resumes == [False]
