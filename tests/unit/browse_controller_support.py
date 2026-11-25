"""What the tests of test_browse_controller share."""

from types import SimpleNamespace
import pytest
from gi.repository import GLib
from delta.daemon import browse_controller
from delta.daemon.browse_controller import BrowseController
from delta.domain.errors import EngineError


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
        connection,
        jobs,
        lambda: stops.append(1),
        lambda owed: resumes.append(owed),
        events,
        on_postponed=lambda: told.append(1),
        usage=usage,
        clock=clock,
    )
    return SimpleNamespace(
        controller=controller,
        jobs=jobs,
        connection=connection,
        events=events,
        stops=stops,
        resumes=resumes,
        watches=watches,
        told=told,
        timers=timers,
        usage=usage,
        clock=clock,
    )


def mount(world, browse, snapshot="abc", sender=":1.42"):
    invocation = Invocation()
    world.controller.mount(browse, GLib.Variant("(s)", (snapshot,)), sender, invocation)
    return invocation


def check(world):
    """One tick of the timer that looks at whether the open folder is still used."""
    return world.timers.added[-1][1]()
