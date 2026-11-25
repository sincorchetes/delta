"""Closing the open folder: when nobody uses it, on sleep, on lock and on shutdown."""

import pytest
from gi.repository import GLib
from delta.daemon import browse_controller
from delta.daemon.browse_controller import BrowseController
from delta.domain.errors import EngineError
from browse_controller_support import Browse, Connection, Invocation, Jobs, ORDER, check, mount
from browse_controller_support import world  # noqa: F401  (fixtures)


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
