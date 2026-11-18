"""Asking the Background portal, and the scheduler that does it once a schedule exists."""

import logging
from datetime import datetime

import pytest
from gi.repository import GLib

from delta.domain.schedule import Schedule
from delta.infrastructure.background_portal import BackgroundPortal
from delta.infrastructure.background_scheduler import BackgroundScheduler


class Connection:
    def __init__(self):
        self.subscribed, self.unsubscribed, self.calls = [], [], []

    def get_unique_name(self):
        return ":1.42"

    def signal_subscribe(self, sender, interface, signal, path, arg0, flags, callback):
        self.subscribed.append((sender, interface, signal, path, callback))
        return 7

    def signal_unsubscribe(self, subscription):
        self.unsubscribed.append(subscription)

    def call(self, name, path, interface, method, parameters, reply_type, flags, timeout, cancellable, callback):
        self.calls.append((name, path, interface, method, parameters.unpack(), callback))

    def call_finish(self, result):
        if isinstance(result, GLib.Error):
            raise result
        return GLib.Variant("(o)", ("/request",))


@pytest.fixture
def world():
    connection, answers = Connection(), []
    portal = BackgroundPortal(connection, token=lambda: "tok")
    portal.request(answers.append)
    return connection, answers


def respond(connection, response, results):
    connection.subscribed[0][-1](None, None, None, None, None, GLib.Variant("(ua{sv})", (response, results)))


def test_it_listens_for_the_reply_on_the_path_the_portal_will_use_before_it_asks(world):
    connection, _answers = world

    sender, interface, signal, path, _callback = connection.subscribed[0]
    assert (sender, interface, signal) == ("org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response")
    assert path == "/org/freedesktop/portal/desktop/request/1_42/tok"  # the unique name without ':' and with '_'


def test_it_asks_to_run_in_the_background_and_to_start_at_login_with_the_daemon_as_command(world):
    connection, _answers = world

    name, path, interface, method, (window, options), _callback = connection.calls[0]
    assert (name, path, interface, method) == (
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Background",
        "RequestBackground",
    )
    assert window == "" and options["handle_token"] == "tok" and options["autostart"] is True
    assert options["commandline"] == ["delta-daemon"] and options["dbus-activatable"] is False
    assert options["reason"]


def test_both_permissions_granted_is_a_yes_and_the_listening_stops(world):
    connection, answers = world

    respond(connection, 0, {"background": GLib.Variant("b", True), "autostart": GLib.Variant("b", True)})

    assert answers == [True] and connection.unsubscribed == [7]


@pytest.mark.parametrize(
    ("response", "results"),
    [
        (1, {"background": True, "autostart": True}),  # the user said no
        (2, {}),  # the request ended some other way
        (0, {"background": True, "autostart": False}),  # allowed to run, not to start at login
        (0, {"background": False, "autostart": True}),
        (0, {}),
    ],
)
def test_anything_less_than_both_is_a_no(world, response, results):
    connection, answers = world

    respond(connection, response, {k: GLib.Variant("b", v) for k, v in results.items()})

    assert answers == [False]


def test_a_portal_that_cannot_be_reached_is_a_no_and_is_logged(world, caplog):
    connection, answers = world

    with caplog.at_level(logging.WARNING):
        connection.calls[0][-1](connection, GLib.Error("no portal", domain="d", code=1))

    assert answers == [False] and connection.unsubscribed == [7] and "background portal" in caplog.text


def test_a_portal_that_accepts_the_request_waits_for_the_signal(world):
    connection, answers = world

    connection.calls[0][-1](connection, "ok")

    assert answers == [] and connection.unsubscribed == []


def test_by_default_every_request_has_its_own_token():
    connection = Connection()
    portal = BackgroundPortal(connection)

    portal.request(lambda granted: None)
    portal.request(lambda granted: None)

    assert connection.subscribed[0][3] != connection.subscribed[1][3]


# --- the scheduler that asks ----------------------------------------------------------------------


class Inner:
    def __init__(self):
        self.applied, self.disabled = [], 0

    def apply(self, schedule):
        self.applied.append(schedule)

    def disable(self):
        self.disabled += 1

    def next_run(self):
        return datetime(2026, 11, 18, 11, 0)


class Portal:
    def __init__(self):
        self.asked = []

    def request(self, on_answer):
        self.asked.append(on_answer)


def test_the_portal_is_asked_the_first_time_a_schedule_is_applied_and_not_again():
    inner, portal = Inner(), Portal()
    scheduler = BackgroundScheduler(inner, portal)

    scheduler.apply(Schedule("hourly"))
    scheduler.apply(Schedule("daily"))

    assert inner.applied == [Schedule("hourly"), Schedule("daily")] and len(portal.asked) == 1


def test_nothing_is_asked_without_a_schedule():
    inner, portal = Inner(), Portal()
    scheduler = BackgroundScheduler(inner, portal)

    scheduler.disable()

    assert inner.disabled == 1 and portal.asked == []


def test_the_next_run_is_the_inner_schedulers():
    assert BackgroundScheduler(Inner(), Portal()).next_run() == datetime(2026, 11, 18, 11, 0)


def test_the_answer_is_logged_either_way(caplog):
    portal = Portal()
    BackgroundScheduler(Inner(), portal).apply(Schedule("hourly"))

    with caplog.at_level(logging.INFO):
        portal.asked[0](True)
        portal.asked[0](False)

    assert "starts at login" in caplog.text and "only happen while it is open" in caplog.text
