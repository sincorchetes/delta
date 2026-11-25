"""What the tests of test_daemon_wiring share."""

from types import SimpleNamespace
import pytest
from delta.daemon import main
from delta.domain.destination import DestinationState


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
        self.callbacks, self.removed = [], []

    def watch(self, callback):
        self.callbacks.append(callback)

    def watch_removed(self, callback):
        self.removed.append(callback)


class Watch:
    """Stands in for DestinationWatch: the probe and the repository it was given, and how often it was told to look."""

    instances: list = []

    def __init__(self, probe, repository):
        self.probe, self.repository, self.looks = probe, repository, 0
        Watch.instances.append(self)

    def state(self):
        return DestinationState.AVAILABLE

    def refresh(self):
        self.looks += 1


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
    Watch.instances = []
    Engine.instances, Service.built, Reloader.instances, Service.resumes = [], [], [], False
    services = SimpleNamespace(preview=Preview(), snapshots=Snapshots(), mounters=[])
    monkeypatch.setattr(main, "LibsecretStore", lambda: "keyring")
    monkeypatch.setattr(main, "BorgRunner", Engine)
    monkeypatch.setattr(main, "BorgMounter", lambda engine: ("mounter", engine))
    monkeypatch.setattr(main, "LogindSessionEvents", lambda: "session events")
    monkeypatch.setattr(main, "GioMountEvents", MountEvents)
    monkeypatch.setattr(main, "LocalDestination", lambda: "probe")
    monkeypatch.setattr(main, "DestinationWatch", Watch)
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
    monkeypatch.setattr(main, "RepositorySetup", lambda engine, store, identity: ("setup", store, identity))
    monkeypatch.setattr(main, "SettingsRepositoryIdentity", lambda: "identity")
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
