"""The daemon is wired together: startup, the bus, stop requests and shutdown."""

import logging
import signal
from types import SimpleNamespace
from gi.repository import Gio, GLib
from delta.daemon import main
from delta.daemon.job_runner import JobRunner
from delta.domain.errors import DeltaError
from delta.domain.repository import Repository
from daemon_wiring_support import Engine, Reloader, Service, Snapshots
from daemon_wiring_support import daemon  # noqa: F401  (fixtures)


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
    assert service.extras["setup"] == ("setup", "keyring", "identity")
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
    assert (
        service.extras["on_cancel"] == Engine.instances[0].interrupt
    )  # cancelling a check stops the engine the same way
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
