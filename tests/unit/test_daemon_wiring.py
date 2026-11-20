"""How the daemon is put together and shut down, with every collaborator replaced by a stand-in."""

import logging
import signal
import threading
from types import SimpleNamespace

import pytest
from gi.repository import Gio, GLib

from delta.application.backup_service import BackupService
from delta.daemon import composition, main
from delta.daemon.job_runner import JobRunner
from delta.daemon.next_run import NextRunCache
from delta.domain.errors import DeltaError
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy


class App:
    def __init__(self):
        self.calls = []

    def hold(self):
        self.calls.append("hold")

    def release(self):
        self.calls.append("release")

    def quit(self):
        self.calls.append("quit")

    def run(self, argv):
        self.calls.append(("run", argv))
        return 7


class Engine:
    instances = []

    def __init__(self, secrets=None):
        self.secrets, self.interrupted = secrets, False
        Engine.instances.append(self)

    def interrupt(self):
        self.interrupted = True


class Preview:
    def __init__(self):
        self.cleared = 0

    def clear(self):
        self.cleared += 1


class Snapshots:
    def __init__(self, error=None):
        self.error = error

    def latest_backup(self):
        if self.error:
            raise self.error
        return 1234


class Service:
    """Stands in for DeltaService: remembers how it was built."""

    resumes = False
    built = []

    def __init__(self, connection, services, extras):
        self.connection, self.services, self.extras = connection, services, extras
        self.reconfigured, self.previews_cleared, self.closed, self.resumed = [], 0, [], []
        Service.built.append(self)

    @classmethod
    def from_services(cls, connection, services, **extras):
        return cls(connection, services, extras)

    def resume_interrupted(self, owed=False):
        self.resumed.append(owed)
        return Service.resumes

    def close_browse(self, reason, resume=True):
        self.closed.append((reason, resume))

    def start_scheduled_backup(self):
        self.scheduled = getattr(self, "scheduled", 0) + 1

    def reconfigure(self, services):
        self.reconfigured.append(services)

    def clear_previews(self):
        self.previews_cleared += 1


class Reloader:
    instances = []

    def __init__(self, settings, jobs, rebuild, scheduler, has_repository):
        self.args = (settings, jobs, rebuild, scheduler, has_repository)
        self.started = False
        Reloader.instances.append(self)

    def start(self):
        self.started = True


class Immediately:
    """A thread that runs its work when started, on the caller's thread."""

    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class MountEvents:
    def __init__(self):
        self.callbacks = []

    def watch(self, callback):
        self.callbacks.append(callback)


class Control:
    """Stands in for BrowseController: remembers what it was given."""

    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs


class Notes(tuple):
    """Stands in for BackupNotifications: the notifier it was given, and the postponed call."""

    @staticmethod
    def postponed():
        return "postponed"


@pytest.fixture
def daemon(monkeypatch):
    Engine.instances, Service.built, Reloader.instances, Service.resumes = [], [], [], False
    services = SimpleNamespace(preview=Preview(), snapshots=Snapshots(), mounters=[])
    monkeypatch.setattr(main, "LibsecretStore", lambda: "keyring")
    monkeypatch.setattr(main, "BorgRunner", Engine)
    monkeypatch.setattr(main, "BorgMounter", lambda engine: ("mounter", engine))
    monkeypatch.setattr(main, "LogindSessionEvents", lambda: "session events")
    monkeypatch.setattr(main, "GioMountEvents", MountEvents)
    monkeypatch.setattr(main, "ProcMountUsage", lambda: "usage")
    monkeypatch.setattr(main, "BrowseController", Control)

    def build(engine, mounter=None):
        services.mounters.append(mounter)
        return services

    monkeypatch.setattr(main, "build_services", build)
    monkeypatch.setattr(main, "SystemdScheduler", lambda: "scheduler")
    monkeypatch.setattr(main, "in_flatpak", lambda: False)
    monkeypatch.setattr(main, "TimerScheduler", lambda trigger, last_backup: ("timer", trigger, last_backup))
    monkeypatch.setattr(main, "BackgroundPortal", lambda connection: ("portal", connection))
    monkeypatch.setattr(main, "BackgroundScheduler", lambda inner, portal: ("background", inner, portal))
    monkeypatch.setattr(main, "RepositorySetup", lambda engine, store: ("setup", store))
    monkeypatch.setattr(main, "BackupNotifications", lambda notifier: Notes(("notifications", notifier)))
    monkeypatch.setattr(main, "GioNotifier", lambda app, opener: ("notifier", app, opener))
    monkeypatch.setattr(main, "FileJobJournal", lambda: "journal")
    monkeypatch.setattr(main, "NextRunCache", lambda scheduler: ("next", scheduler))
    monkeypatch.setattr(main, "DeltaService", Service)
    monkeypatch.setattr(main, "ConfigReloader", Reloader)
    monkeypatch.setattr(main, "threading", SimpleNamespace(Thread=Immediately))
    monkeypatch.setattr(main, "open_settings", lambda: None)
    instance = main.DeltaDaemon()
    instance._app = App()
    instance.services = services
    return instance


# --- starting up ---------------------------------------------------------------------------------


def test_startup_holds_the_app_follows_the_stop_signals_and_owns_the_bus_name(daemon, monkeypatch):
    seen = {"signals": [], "bus": []}
    monkeypatch.setattr(main, "watch_signal", lambda signum, handler: seen["signals"].append((signum, handler)))
    monkeypatch.setattr(
        main,
        "Gio",
        SimpleNamespace(
            BusType=Gio.BusType,
            BusNameOwnerFlags=Gio.BusNameOwnerFlags,
            bus_own_name=lambda *args: seen["bus"].append(args),
        ),
    )

    daemon._on_startup(daemon._app)

    assert daemon._app.calls == ["hold"]
    assert [signum for signum, _handler in seen["signals"]] == [signal.SIGTERM, signal.SIGINT]
    assert all(handler == daemon._on_terminate for _signum, handler in seen["signals"])
    assert seen["bus"][0][1] == "io.github.sincorchetes.Delta.Service1"


def test_the_bus_is_served_with_the_services_the_configuration_builds(daemon):
    daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")

    service = Service.built[0]
    assert service.connection == "connection" and service.services is daemon.services
    assert service.extras["setup"] == ("setup", "keyring")
    assert service.extras["journal"] == "journal" and service.extras["next_runs"] == ("next", "scheduler")
    assert service.extras["notifications"][1][2] is main.open_ui
    assert Engine.instances[0].secrets == "keyring"
    assert daemon.services.preview.cleared == 1  # what a daemon that was killed left behind


def test_the_last_backup_is_taken_from_the_repository_at_startup(daemon):
    daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")

    assert daemon._jobs.last_backup == 1234


def test_an_interrupted_backup_is_resumed_at_startup(daemon, caplog):
    Service.resumes = True

    with caplog.at_level(logging.INFO):
        daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")

    assert "resuming the backup" in caplog.text


def test_without_the_settings_schema_nothing_follows_the_configuration(daemon):
    daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")

    assert Reloader.instances == [] and daemon._reloader is None


def test_with_settings_the_configuration_is_followed_and_rebuilt_on_change(daemon, monkeypatch):
    monkeypatch.setattr(main, "open_settings", lambda: "settings")
    monkeypatch.setattr(main, "configured_repository", lambda: Repository("/r"))

    daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")

    reloader = Reloader.instances[0]
    settings, jobs, rebuild, scheduler, has_repository = reloader.args
    assert reloader.started and settings == "settings" and jobs is daemon._jobs and scheduler == "scheduler"
    assert has_repository() is True
    rebuild()
    assert Service.built[0].reconfigured == [daemon.services]
    assert Service.built[0].closed == [("repository-changed", False)]
    assert daemon.services.mounters == [daemon._mounter, daemon._mounter]


def test_a_native_install_schedules_with_systemd_and_mounts_backups(daemon):
    daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")

    service = Service.built[0]
    assert service.extras["next_runs"] == ("next", "scheduler")
    assert daemon.services.mounters == [("mounter", Engine.instances[0])]
    assert service.extras["browse_control"].args[4] == "session events"


def test_in_a_flatpak_the_daemon_keeps_the_time_itself_and_mounts_nothing(daemon, monkeypatch):
    monkeypatch.setattr(main, "in_flatpak", lambda: True)

    daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")

    service = Service.built[0]
    kind, scheduler = service.extras["next_runs"]
    background, inner, portal = scheduler
    name, trigger, last_backup = inner
    assert kind == "next" and background == "background" and name == "timer"
    assert portal == ("portal", "connection")  # the portal is asked over the daemon's own bus connection
    assert daemon.services.mounters == [None] and daemon._mounter is None
    assert service.extras["browse_control"].args[4] is None  # no sleep or lock to wait for: nothing is mounted
    assert last_backup() == daemon._jobs.last_backup == 1234  # what the daemon learnt from the repository
    trigger()
    assert service.scheduled == 1  # the schedule asks the service, not D-Bus


def test_browsing_is_wired_to_the_engine_the_jobs_and_the_session(daemon):
    daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")

    service = Service.built[0]
    connection, jobs, interrupt, resume, events = service.extras["browse_control"].args
    assert connection == "connection" and jobs is daemon._jobs and events == "session events"
    assert service.extras["browse_control"].kwargs["on_postponed"] == service.extras["notifications"].postponed
    assert service.extras["browse_control"].kwargs["usage"] == "usage"
    assert interrupt == Engine.instances[0].interrupt
    assert daemon.services.mounters == [("mounter", Engine.instances[0])]
    resume(True)
    assert service.resumed == [False, True]  # the startup check, then the one browsing asked for


def test_no_repository_means_the_schedule_is_switched_off(daemon, monkeypatch):
    monkeypatch.setattr(main, "open_settings", lambda: "settings")
    monkeypatch.setattr(main, "configured_repository", lambda: None)

    daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")

    assert Reloader.instances[0].args[4]() is False


def test_a_repository_that_cannot_be_read_at_startup_is_not_fatal(daemon, caplog):
    daemon._jobs = JobRunner(None)

    with caplog.at_level(logging.INFO):
        daemon._seed_last_backup(Snapshots(DeltaError("locked")))

    assert "could not read the last backup" in caplog.text and daemon._jobs.last_backup == 0


# --- shutting down -------------------------------------------------------------------------------


def test_a_stop_request_with_nothing_running_quits_at_once(daemon):
    assert daemon._on_terminate() is GLib.SOURCE_REMOVE

    assert daemon._app.calls == ["quit"]


def test_a_stop_request_interrupts_borg_and_quits_once_idle(daemon):
    daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")

    daemon._on_terminate()

    assert Engine.instances[0].interrupted and daemon._app.calls == ["quit"]
    assert Service.built[0].closed == [("shutdown", False)]  # the folder never outlives the daemon


def test_losing_the_bus_name_lets_go_of_the_app(daemon):
    daemon._on_name_lost("connection", "io.github.sincorchetes.Delta.Service1")

    assert daemon._app.calls == ["release"]


def test_shutdown_forgets_the_previews_only_when_there_is_a_service(daemon):
    daemon._on_shutdown(daemon._app)
    daemon._on_bus_acquired("connection", "io.github.sincorchetes.Delta.Service1")
    daemon._on_shutdown(daemon._app)

    assert Service.built[0].previews_cleared == 1


def test_run_returns_what_the_application_returns(daemon):
    assert daemon.run() == 7
    assert daemon._app.calls == [("run", None)]


def test_main_sets_up_logging_and_translations_and_runs_the_daemon(monkeypatch):
    steps = []
    monkeypatch.setattr(main.logging, "basicConfig", lambda **kwargs: steps.append("logging"))
    monkeypatch.setattr(main.i18n, "setup", lambda: steps.append("i18n"))
    monkeypatch.setattr(main, "DeltaDaemon", lambda: SimpleNamespace(run=lambda: 3))

    assert main.main() == 3
    assert steps == ["logging", "i18n"]


# --- composition ---------------------------------------------------------------------------------


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


# --- jobs and the next run -----------------------------------------------------------------------


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
    (on_mounted,) = daemon._mount_events.callbacks
    service = Service.built[0]

    on_mounted()  # nothing is waiting: the status is idle
    assert not hasattr(service, "scheduled")

    daemon._jobs.unavailable = "/media/disk/delta"
    on_mounted()
    assert service.scheduled == 1
