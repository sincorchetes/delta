"""Entry point of the Delta D-Bus daemon."""

import logging
import signal
import threading

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLibUnix", "2.0")
from gi.repository import Gio, GLib, GLibUnix

from delta import i18n
from delta.application.backup_notifications import BackupNotifications
from delta.application.repository_setup import RepositorySetup
from delta.daemon.browse_controller import REASON_REPOSITORY_CHANGED, REASON_SHUTDOWN, BrowseController
from delta.daemon.composition import build_services
from delta.daemon.config_reloader import ConfigReloader
from delta.daemon.introspection import INTERFACE_NAME
from delta.daemon.job_runner import JobRunner
from delta.daemon.next_run import NextRunCache
from delta.daemon.service import DeltaService
from delta.domain.errors import DeltaError
from delta.infrastructure.background_portal import BackgroundPortal
from delta.infrastructure.background_scheduler import BackgroundScheduler
from delta.infrastructure.borg_mounter import BorgMounter
from delta.infrastructure.borg_runner import BorgRunner
from delta.infrastructure.file_job_journal import FileJobJournal
from delta.infrastructure.gio_notifier import GioNotifier
from delta.infrastructure.libsecret_store import LibsecretStore
from delta.infrastructure.proc_mount_usage import ProcMountUsage
from delta.infrastructure.runtime import in_flatpak
from delta.infrastructure.session_events import LogindSessionEvents
from delta.infrastructure.settings import configured_repository, open_settings, save_repository
from delta.infrastructure.systemd_scheduler import SystemdScheduler
from delta.infrastructure.timer_scheduler import TimerScheduler
from delta.infrastructure.ui_launcher import open_ui

# Not io.github.sincorchetes.Delta: that id belongs to the GTK app, and sharing it would make
# launching the app hand its activation to this windowless daemon.
APPLICATION_ID = "io.github.sincorchetes.Delta.Daemon"
log = logging.getLogger(__name__)


class DeltaDaemon:
    """Owns io.github.sincorchetes.Delta.Service1 on the session bus until the name is lost.

    A Gio.Application (not a bare main loop) so Gio.Notification works and a
    second instance hands over to the running one.
    """

    def __init__(self) -> None:
        self._app = Gio.Application.new(APPLICATION_ID, Gio.ApplicationFlags.DEFAULT_FLAGS)
        self._app.connect("startup", self._on_startup)
        self._app.connect("activate", lambda app: None)
        self._app.connect("shutdown", self._on_shutdown)
        self._service = None
        self._reloader = None
        self._engine = None
        self._mounter = None
        self._jobs = None

    def run(self) -> int:
        return self._app.run(None)

    def _on_startup(self, app) -> None:
        app.hold()
        for signum in (signal.SIGTERM, signal.SIGINT):
            GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signum, self._on_terminate)
        Gio.bus_own_name(
            Gio.BusType.SESSION,
            INTERFACE_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired,
            None,
            self._on_name_lost,
        )

    def _on_bus_acquired(self, connection, name) -> None:
        store = LibsecretStore()
        self._engine = BorgRunner(secrets=store)
        sandboxed = in_flatpak()  # no FUSE that the file manager can see, no systemd --user
        self._mounter = None if sandboxed else BorgMounter(self._engine)
        services, jobs = build_services(self._engine, self._mounter), JobRunner(connection)
        self._jobs = jobs
        scheduler = (
            BackgroundScheduler(
                TimerScheduler(lambda: self._service.start_scheduled_backup(), lambda: jobs.last_backup),
                BackgroundPortal(connection),
            )
            if sandboxed
            else SystemdScheduler()
        )
        notifications = BackupNotifications(GioNotifier(self._app, open_ui))
        self._service = DeltaService.from_services(
            connection,
            services,
            jobs=jobs,
            browse_control=BrowseController(
                connection,
                jobs,
                self._engine.interrupt,
                lambda owed: self._service.resume_interrupted(owed),
                None if sandboxed else LogindSessionEvents(),
                on_postponed=notifications.postponed,
                usage=ProcMountUsage(),
            ),
            setup=RepositorySetup(self._engine, store),
            on_repository_created=save_repository,
            notifications=notifications,
            journal=FileJobJournal(),
            next_runs=NextRunCache(scheduler),
        )
        services.preview.clear()  # leftovers of a daemon that was killed
        if self._service.resume_interrupted():
            log.info("resuming the backup that was interrupted")
        threading.Thread(target=self._seed_last_backup, args=(services.snapshots,), daemon=True).start()
        settings = open_settings()
        if settings is not None:
            self._reloader = ConfigReloader(
                settings,
                jobs,
                self._rebuild,
                scheduler,
                lambda: configured_repository() is not None,
            )
            self._reloader.start()

    def _seed_last_backup(self, snapshots) -> None:
        """After a restart the daemon remembers nothing: ask the repository when it was last backed up."""
        try:
            self._jobs.seed_last_backup(snapshots.latest_backup())
        except DeltaError as err:
            log.info("could not read the last backup from the repository: %s", err)

    def _on_terminate(self) -> bool:
        """Shutdown: stop borg cleanly, leave the journal mark, exit once idle."""
        if self._engine is not None:
            self._engine.interrupt()
        if self._service is not None:
            self._service.close_browse(REASON_SHUTDOWN, resume=False)
        if self._jobs is not None:
            self._jobs.when_idle(self._app.quit)
        else:
            self._app.quit()
        return GLib.SOURCE_REMOVE

    def _rebuild(self) -> None:
        self._service.close_browse(REASON_REPOSITORY_CHANGED, resume=False)
        self._service.reconfigure(build_services(self._engine, self._mounter))

    def _on_name_lost(self, connection, name) -> None:
        self._app.release()

    def _on_shutdown(self, app) -> None:
        if self._service is not None:
            self._service.clear_previews()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    i18n.setup()
    return DeltaDaemon().run()
