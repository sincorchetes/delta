"""What the daemon builds from the configuration and the platform: folders, services, tasks and drives."""

import logging
import threading
import pytest
from gi.repository import GLib
from delta.application.backup_service import BackupService
from delta.daemon import composition, main
from delta.daemon.job_runner import JobRunner
from delta.daemon.next_run import NextRunCache
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy
from daemon_wiring_support import Service, Watch
from daemon_wiring_support import daemon  # noqa: F401  (fixtures)


def test_previews_live_in_the_volatile_runtime_folder():
    assert composition.preview_root().endswith("/delta/preview")


def test_in_a_flatpak_previews_go_to_the_cache_folder_so_that_the_portals_can_share_them(monkeypatch):
    monkeypatch.setattr(composition, "in_flatpak", lambda: False)
    assert composition.preview_root() == f"{GLib.get_user_runtime_dir()}/delta/preview"

    monkeypatch.setattr(composition, "in_flatpak", lambda: True)
    assert composition.preview_root() == f"{GLib.get_user_cache_dir()}/delta/preview"


def test_snapshots_open_in_a_private_volatile_folder():
    assert composition.browse_root().endswith("/delta/browse")


def test_browsing_exists_only_where_there_is_a_mounter(monkeypatch):
    monkeypatch.setattr(composition, "configured_repository", lambda: Repository("/r"))
    monkeypatch.setattr(composition, "configured_sources", lambda: ())
    monkeypatch.setattr(composition, "configured_excludes", lambda: ())
    monkeypatch.setattr(composition, "configured_retention", lambda: RetentionPolicy())

    assert composition.build_services(object()).browse is None
    assert composition.build_services(object(), mounter=object()).browse is not None


def test_the_services_are_built_from_the_current_configuration(monkeypatch):
    monkeypatch.setattr(composition, "configured_repository", lambda: Repository("/r"))
    monkeypatch.setattr(composition, "configured_sources", lambda: ("/data",))
    monkeypatch.setattr(composition, "configured_excludes", lambda: ("/data/tmp",))
    monkeypatch.setattr(composition, "configured_retention", lambda: RetentionPolicy())

    services = composition.build_services(object())

    assert isinstance(services.backup, BackupService)
    assert services.backup.new_job().sources == ("/data",)
    assert "pp:/data/tmp" in services.backup.new_job().excludes


def test_no_chosen_folders_means_the_whole_home_folder():
    assert composition.resolve_sources((), "/home/u") == ("/home/u",)


def test_a_relative_folder_is_ignored_and_never_widened_to_home(caplog):
    with caplog.at_level(logging.WARNING):
        assert composition.resolve_sources(("docs", "/data", "/data"), "/home/u") == ("/data",)
        assert composition.resolve_sources(("docs",), "/home/u") == ()

    assert "not an absolute path" in caplog.text


def test_a_relative_exclusion_is_ignored(caplog):
    with caplog.at_level(logging.WARNING):
        excludes = composition.resolve_excludes(("tmp", "/data/cache"), "/home/u")

    assert "pp:/data/cache" in excludes and not any("tmp" in e for e in excludes)
    assert "ignoring exclusion" in caplog.text


def test_a_scheduler_that_breaks_means_no_known_next_run():
    class Broken:
        def next_run(self):
            raise RuntimeError("systemd is gone")

    cache = NextRunCache(Broken(), spawn=lambda work: work())

    assert cache.value() == 0
    assert cache.value() == 0


def test_a_task_that_crashes_is_logged_and_does_not_leave_the_daemon_busy(caplog):
    runner = JobRunner(None)
    runner._emit = lambda *args: None
    runner._running = True

    def crash(progress):
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError):
        runner._work("job", crash, True)

    assert "crashed" in caplog.text
    assert runner.status == "idle" and runner.last_error == "unexpected error"


def test_the_next_run_is_looked_up_on_a_background_thread_by_default():
    asked = threading.Event()

    class Scheduler:
        def next_run(self):
            asked.set()

    NextRunCache(Scheduler()).value()

    assert asked.wait(5)


def test_a_drive_that_is_mounted_starts_the_backup_that_was_waiting_for_it(daemon):
    daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")
    on_mounted, _ = daemon._mount_events.callbacks
    service = Service.built[0]

    on_mounted()  # nothing is waiting: the status is idle
    assert not hasattr(service, "scheduled")

    daemon._jobs.unavailable = "/media/disk/delta"
    on_mounted()
    assert service.scheduled == 1


def test_the_place_of_the_backups_is_looked_at_from_the_start_and_whenever_a_drive_comes_or_goes(daemon):
    daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")
    (watch,) = Watch.instances

    assert (watch.probe, watch.repository, watch.looks) == ("probe", main.configured_repository, 1)

    _, looked = daemon._mount_events.callbacks
    (gone,) = daemon._mount_events.removed
    looked()
    gone()

    assert watch.looks == 3 and looked == gone == watch.refresh


def test_what_exists_is_handed_back_and_what_does_not_is_said():
    assert main._required("here", "the thing") == "here"
    with pytest.raises(RuntimeError, match="the thing is not there yet"):
        main._required(None, "the thing")


def test_nothing_that_needs_the_service_runs_before_it_is_there(daemon):
    with pytest.raises(RuntimeError, match="the service is not there yet"):
        daemon._start_scheduled()
    with pytest.raises(RuntimeError, match="the service is not there yet"):
        daemon._rebuild()


def test_the_scheduler_asks_the_service_for_a_scheduled_backup(daemon):
    daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")

    daemon._start_scheduled()

    assert Service.built[0].scheduled == 1
