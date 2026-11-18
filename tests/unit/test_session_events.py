"""Sleep and screen lock both close an open snapshot; any other change of those signals does not."""

import logging
import os
from types import SimpleNamespace

from gi.repository import Gio, GLib

from delta.infrastructure import session_events
from delta.infrastructure.session_events import LogindSessionEvents


class FdList:
    def __init__(self, fd):
        self.fd = fd

    def get(self, index):
        return self.fd


class Bus:
    def __init__(self, fd=None, error=None):
        self.subscribed, self.inhibited, self.fd, self.error = [], [], fd, error

    def signal_subscribe(self, name, interface, signal, path, arg0, flags, handler, data):
        self.subscribed.append((name, interface, signal, handler, data))

    def call_with_unix_fd_list_sync(
        self, name, path, interface, method, parameters, reply_type, flags, timeout, fds, cancellable
    ):
        if self.error:
            raise self.error
        self.inhibited.append((name, method, parameters.unpack()))
        return GLib.Variant("(h)", (0,)), FdList(self.fd)


def fake_gio(monkeypatch, buses):
    def get(bus_type, cancellable):
        bus = buses[bus_type]
        if isinstance(bus, Exception):
            raise bus
        return bus

    monkeypatch.setattr(
        session_events,
        "Gio",
        SimpleNamespace(
            BusType=Gio.BusType,
            DBusCallFlags=Gio.DBusCallFlags,
            DBusSignalFlags=Gio.DBusSignalFlags,
            bus_get_sync=get,
        ),
    )


def open_descriptor():
    read_end, write_end = os.pipe()
    os.close(write_end)
    return read_end


def is_open(fd):
    try:
        os.fstat(fd)
    except OSError:
        return False
    return True


def test_it_asks_logind_to_delay_sleeping_and_lets_go_when_told(monkeypatch):
    fd = open_descriptor()
    system = Bus(fd=fd)
    fake_gio(monkeypatch, {Gio.BusType.SYSTEM: system})
    events = LogindSessionEvents()

    events.hold()
    events.hold()  # already held: not asked twice

    assert len(system.inhibited) == 1 and is_open(fd)
    name, method, (what, who, why, mode) = system.inhibited[0]
    assert (name, method, what, who, mode) == ("org.freedesktop.login1", "Inhibit", "sleep", "Delta", "delay")
    assert why

    events.release()
    events.release()  # nothing held any more: harmless

    assert not is_open(fd)


def test_letting_go_without_having_held_does_nothing():
    LogindSessionEvents().release()


def test_a_logind_that_refuses_is_logged_and_there_is_nothing_to_release(monkeypatch, caplog):
    fake_gio(monkeypatch, {Gio.BusType.SYSTEM: Bus(error=GLib.Error("no logind"))})
    events = LogindSessionEvents()

    with caplog.at_level(logging.WARNING):
        events.hold()

    assert "cannot delay sleeping" in caplog.text and events._lock_fd is None
    events.release()


def test_it_listens_for_sleep_on_the_system_bus_and_for_the_lock_on_the_session_bus(monkeypatch):
    system, session = Bus(), Bus()
    fake_gio(monkeypatch, {Gio.BusType.SYSTEM: system, Gio.BusType.SESSION: session})

    LogindSessionEvents().watch(lambda: None)

    assert [s[:3] for s in system.subscribed] == [
        ("org.freedesktop.login1", "org.freedesktop.login1.Manager", "PrepareForSleep")
    ]
    assert [s[:3] for s in session.subscribed] == [
        ("org.gnome.ScreenSaver", "org.gnome.ScreenSaver", "ActiveChanged")
    ]


def test_only_the_beginning_of_a_sleep_or_a_lock_is_reported(monkeypatch):
    bus, calls = Bus(), []
    fake_gio(monkeypatch, {Gio.BusType.SYSTEM: bus, Gio.BusType.SESSION: Bus()})
    LogindSessionEvents().watch(lambda: calls.append(1))
    handler, data = bus.subscribed[0][3], bus.subscribed[0][4]

    handler(None, None, None, None, None, GLib.Variant("(b)", (False,)), data)
    assert calls == []
    handler(None, None, None, None, None, GLib.Variant("(b)", (True,)), data)
    assert calls == [1]


def test_a_bus_that_cannot_be_reached_is_logged_and_the_other_still_watched(monkeypatch, caplog):
    session = Bus()
    fake_gio(monkeypatch, {Gio.BusType.SYSTEM: GLib.Error("no system bus"), Gio.BusType.SESSION: session})

    with caplog.at_level(logging.WARNING):
        LogindSessionEvents().watch(lambda: None)

    assert "PrepareForSleep" in caplog.text and len(session.subscribed) == 1
