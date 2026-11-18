"""The corners of the service object: calls it cannot serve, shutting down twice, resuming with nothing to back up."""

from types import SimpleNamespace

from conftest import call_rows
from gi.repository import GLib

from delta.application.backup_service import BackupService
from delta.application.snapshot_service import SnapshotService
from delta.daemon.job_runner import JobRunner
from delta.daemon.service import DeltaService
from delta.domain.repository import Repository


class Engine:
    def list_snapshots(self, repo):
        return []


class Journal:
    def was_interrupted(self):
        return True


def bare_service(bus, **services):
    return DeltaService(bus, SnapshotService(Engine(), Repository("/r")), **services)


def test_a_backup_asked_of_a_daemon_without_backups_is_unavailable(bus):
    service = bare_service(bus)

    outcome = call_rows(bus, "CreateBackup", None)
    service.unregister()

    assert "Unavailable" in outcome["error"]


def test_unlocking_without_the_service_is_unavailable(bus):
    service = bare_service(bus)

    outcome = call_rows(bus, "UnlockRepository", None)
    service.unregister()

    assert "Unavailable" in outcome["error"]


def test_browsing_without_a_mounter_is_unavailable_and_says_it_cannot_mount(bus):
    service = bare_service(bus)

    mount = call_rows(bus, "MountSnapshot", GLib.Variant("(s)", ("first",)))
    unmount = call_rows(bus, "UnmountSnapshot", None)
    can_mount = service._on_get_property(None, None, None, None, "CanMount")
    service.unregister()

    assert "Unavailable" in mount["error"] and "Unavailable" in unmount["error"]
    assert can_mount.unpack() is False


def test_an_unknown_property_has_no_value(bus):
    service = bare_service(bus)

    assert service._on_get_property(None, None, None, None, "Nope") is None
    service.unregister()


def test_shutting_down_twice_is_harmless(bus):
    service = bare_service(bus)

    service.unregister()
    service.unregister()


def test_forgetting_previews_without_a_preview_service_does_nothing(bus):
    service = bare_service(bus)

    service.clear_previews()
    service.unregister()


def test_closing_the_browser_without_one_does_nothing_and_with_one_passes_it_on(bus):
    closed = []
    bare = bare_service(bus)
    bare.close_browse("shutdown")
    bare.unregister()

    service = bare_service(bus, browse_control=SimpleNamespace(close=lambda *args: closed.append(args)))
    service.close_browse("shutdown", resume=False)
    service.unregister()

    assert closed == [("shutdown", False)]


def test_a_scheduled_backup_starts_like_a_requested_one_and_waits_for_an_open_snapshot(bus):
    created = []

    class Recording(Engine):
        def create(self, repo, job, name=None, on_progress=None):
            created.append(job.id)
            return "archive"

    class Browsing:
        def __init__(self, open_now):
            self.open_now = open_now

        def postpone(self):
            return self.open_now

    service = bare_service(
        bus, jobs=JobRunner(bus), backup=BackupService(Recording(), Repository("/r"), ("/home",)),
        browse_control=Browsing(open_now=True),
    )
    assert service.start_scheduled_backup() is False and created == []  # postponed, not started

    service._browse_control = Browsing(open_now=False)
    assert service.start_scheduled_backup() is True
    service.unregister()


def test_a_scheduled_backup_where_nothing_can_be_browsed_just_starts(bus):
    class Creating(Engine):
        def create(self, repo, job, name=None, on_progress=None):
            return "archive"

    service = bare_service(
        bus, jobs=JobRunner(bus), backup=BackupService(Creating(), Repository("/r"), ("/home",))
    )

    assert service._browse_control is None and service.start_scheduled_backup() is True
    service.unregister()


def test_a_scheduled_backup_in_a_daemon_that_cannot_back_up_is_not_started(bus):
    service = bare_service(bus)

    assert service.start_scheduled_backup() is False
    service.unregister()


def test_nothing_is_resumed_by_a_daemon_that_cannot_back_up(bus):
    service = bare_service(bus)

    assert service.resume_interrupted(owed=True) is False
    service.unregister()


def test_a_turned_away_backup_runs_even_when_there_is_no_journal(bus):
    created = []

    class Recording(Engine):
        def create(self, repo, job, name=None, on_progress=None):
            created.append(job.id)
            return "archive"

    service = bare_service(
        bus, jobs=JobRunner(bus), backup=BackupService(Recording(), Repository("/r"), ("/home",))
    )

    assert service.resume_interrupted() is False  # nothing interrupted, nothing owed
    assert service.resume_interrupted(owed=True) is True
    service.unregister()


def test_an_interrupted_backup_is_not_resumed_when_there_is_nothing_to_back_up(bus):
    service = bare_service(
        bus,
        jobs=JobRunner(bus),
        backup=BackupService(Engine(), Repository("/r"), sources=()),
        journal=Journal(),
    )

    assert service.resume_interrupted() is False
    service.unregister()
