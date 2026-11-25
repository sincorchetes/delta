"""Opening a snapshot wins over backing up, with the jobs, the bus and the mount replaced by stand-ins."""

import pytest
from delta.domain.errors import DeltaError
from browse_controller_support import Browse, mount
from browse_controller_support import world  # noqa: F401  (fixtures)


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
