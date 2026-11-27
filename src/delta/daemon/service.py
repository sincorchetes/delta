"""D-Bus service object for the Delta daemon."""

import dataclasses
import uuid
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from delta.application.backup_notifications import BackupNotifications
from delta.application.backup_service import BackupService
from delta.application.browse_service import BrowseService
from delta.application.check_service import CheckService
from delta.application.deleted_service import DeletedService
from delta.application.ports import JobJournal
from delta.application.preview_service import PreviewService
from delta.application.prune_service import PruneService
from delta.application.repository_setup import RepositorySetup
from delta.application.restore_service import RestoreService
from delta.application.snapshot_service import SnapshotService
from delta.application.unlock_service import UnlockService
from delta.application.version_service import VersionService
from delta.daemon.browse_controller import BrowseController
from delta.daemon.composition import Services
from delta.daemon.backup_task import make_backup_task
from delta.daemon.introspection import INTERFACE_XML, OBJECT_PATH
from delta.daemon.job_calls import (
    ERROR_BUSY,
    ERROR_INVALID_ARGUMENT,
    ERROR_UNAVAILABLE,
    cancel_check,
    start_check,
    start_preview,
    start_restore,
    start_restore_beside,
    start_restore_deleted,
    start_unlock,
    submit_job,
)
from delta.daemon.job_runner import JobAlreadyRunning, JobRunner, Task
from delta.daemon.next_run import NextRunCache
from delta.daemon.query_calls import (
    list_changed,
    list_deleted,
    list_folder,
    list_versions,
    run_query,
    search_folder,
)
from delta.daemon.variants import snapshot_to_variant
from delta.domain.errors import DeltaError
from delta.domain.repository import Repository
from delta.i18n import _


class DeltaService:
    """Exposes io.github.sincorchetes.Delta.Service1 on the session bus.

    Unwired optional services answer Unavailable (e.g. MountSnapshot without a mounter).
    """

    def __init__(
        self,
        connection: Gio.DBusConnection,
        snapshots: SnapshotService,
        jobs: JobRunner | None = None,
        backup: BackupService | None = None,
        restore: RestoreService | None = None,
        versions: VersionService | None = None,
        prune: PruneService | None = None,
        setup: RepositorySetup | None = None,
        on_repository_created: Callable[[Repository], None] | None = None,
        notifications: BackupNotifications | None = None,
        journal: JobJournal | None = None,
        next_runs: NextRunCache | None = None,
        unlock: UnlockService | None = None,
        preview: PreviewService | None = None,
        deleted: DeletedService | None = None,
        browse: BrowseService | None = None,
        browse_control: BrowseController | None = None,
        check: CheckService | None = None,
        on_cancel: Callable[[], None] = lambda: None,
    ) -> None:
        self._connection = connection
        self._browse = browse
        self._browse_control = browse_control
        self._preview = preview
        self._deleted = deleted
        self._unlock = unlock
        self._check = check
        self._on_cancel = on_cancel
        self._next_runs = next_runs
        self._journal = journal
        self._notifications = notifications
        self._setup = setup
        self._on_repository_created = on_repository_created
        self._prune = prune
        self._versions = versions
        self._snapshots = snapshots
        self._jobs = jobs
        self._backup = backup
        self._restore = restore
        node_info = Gio.DBusNodeInfo.new_for_xml(INTERFACE_XML)
        self._registration_id = connection.register_object(
            OBJECT_PATH,
            node_info.interfaces[0],
            self._on_method_call,
            self._on_get_property,
            None,
        )

    @classmethod
    def from_services(cls, connection: Gio.DBusConnection, services: Services, **extras) -> "DeltaService":
        """Start with every service the configuration builds. Each field of `Services` is a
        constructor argument of the same name, so a service added later cannot be left out."""
        return cls(connection, **{f.name: getattr(services, f.name) for f in dataclasses.fields(services)}, **extras)

    def reconfigure(self, services: Services) -> None:
        """Swap config-dependent services; running jobs keep the ones they hold."""
        for field in dataclasses.fields(services):
            setattr(self, f"_{field.name}", getattr(services, field.name))

    def unregister(self) -> None:
        if self._registration_id:
            self._connection.unregister_object(self._registration_id)
            self._registration_id = 0

    def _on_method_call(
        self, connection, sender, object_path, interface_name, method_name, parameters, invocation
    ) -> None:
        if method_name == "ListSnapshots":
            self._list_snapshots_async(invocation)
        elif method_name == "CreateBackup":
            self._create_backup(invocation)
        elif method_name == "UnlockRepository":
            start_unlock(self._jobs, self._unlock, invocation)
        elif method_name == "CheckRepository":
            start_check(self._jobs, self._check, invocation)
        elif method_name == "CancelCheck":
            cancel_check(self._jobs, self._on_cancel, invocation)
        elif method_name in ("CreateRepository", "UseRepository"):
            self._create_repository(parameters, invocation, method_name == "UseRepository")
        elif method_name == "Restore":
            start_restore(self._jobs, self._restore, parameters, invocation)
        elif method_name in ("RestoreAsCopy", "RestoreReplace"):
            start_restore_beside(
                self._jobs, self._restore, parameters, invocation, method_name == "RestoreReplace"
            )
        elif method_name == "PreviewVersion":
            start_preview(self._jobs, self._preview, parameters, invocation)
        elif method_name == "ClearPreviews":
            self._clear_previews(invocation)
        elif method_name in ("MountSnapshot", "UnmountSnapshot"):
            self._browse_call(method_name, parameters, sender, invocation)
        elif method_name == "ListVersions":
            list_versions(self._versions, parameters, invocation)
        elif method_name == "ListFolder":
            list_folder(self._versions, parameters, invocation)
        elif method_name == "SearchFolder":
            search_folder(self._versions, parameters, invocation)
        elif method_name == "ListDeleted":
            list_deleted(self._deleted, parameters, invocation)
        elif method_name == "ListChanged":
            list_changed(self._deleted, parameters, invocation)
        else:  # RestoreDeleted: the interface declares no other method
            start_restore_deleted(self._jobs, self._deleted, parameters, invocation)

    def _create_backup(self, invocation) -> None:
        jobs, backup = self._jobs, self._backup
        if jobs is None or backup is None:
            invocation.return_dbus_error(ERROR_UNAVAILABLE, _("backups are not available"))
            return
        if self._browse_control is not None and self._browse_control.postpone():
            invocation.return_dbus_error(
                ERROR_BUSY, _("A backup is open as a folder. The new copy will start when you close it.")
            )
            return
        try:
            job_id, task = self._backup_task(backup)
        except ValueError as err:
            invocation.return_dbus_error(ERROR_INVALID_ARGUMENT, str(err))
            return
        self._submit(jobs, invocation, job_id, task, records_backup=True)

    def start_scheduled_backup(self) -> bool:
        """A backup the schedule asks for. No D-Bus caller to answer: the rules are those of CreateBackup
        (a snapshot open as a folder postpones it, a job already running means it is not started)."""
        if self._browse_control is not None and self._browse_control.postpone():
            return False
        return self.resume_interrupted(owed=True)

    def _browse_call(self, method_name, parameters, sender, invocation) -> None:
        control = self._browse_control
        if control is None:
            invocation.return_dbus_error(ERROR_UNAVAILABLE, _("browsing backups is not available"))
        elif method_name == "MountSnapshot":
            control.mount(self._browse, parameters, sender, invocation)
        else:
            control.unmount(invocation)

    def close_browse(self, reason: str, resume: bool = True) -> None:
        """Close the open snapshot, if any (shutdown, new configuration)."""
        if self._browse_control is not None:
            self._browse_control.close(reason, resume)

    def _backup_task(self, backup: BackupService) -> tuple[str, Task]:
        job = backup.new_job()
        task = make_backup_task(job, backup, self._prune, self._notifications, self._journal)
        return job.id, task

    def resume_interrupted(self, owed: bool = False) -> bool:
        """Start a backup if the previous one was cut short (shutdown, crash, a snapshot opened)
        or if one was turned away meanwhile (`owed`)."""
        jobs, backup, journal = self._jobs, self._backup, self._journal
        if jobs is None or backup is None:
            return False
        if not owed and (journal is None or not journal.was_interrupted()):
            return False
        try:
            job_id, task = self._backup_task(backup)
            jobs.submit(job_id, task, records_backup=True)
        except ValueError:
            return False  # no valid backup sources configured
        except JobAlreadyRunning:
            return False
        return True

    def _create_repository(self, parameters, invocation, adopt: bool = False) -> None:
        """Create: an empty passphrase is generated and never leaves the daemon.
        Adopt: an existing repository, which needs its passphrase and is never re-initialised."""
        jobs, setup = self._jobs, self._setup
        if jobs is None or setup is None:
            invocation.return_dbus_error(
                ERROR_UNAVAILABLE, _("repository setup is not available")
            )
            return
        location, passphrase = parameters.unpack()
        try:
            if adopt and not passphrase:
                raise ValueError(_("An existing repository needs its passphrase."))
            repo = Repository(location)
        except ValueError as err:
            invocation.return_dbus_error(ERROR_INVALID_ARGUMENT, str(err))
            return

        created, notes = self._on_repository_created, self._notifications

        def task(on_progress):
            try:
                if adopt:
                    jobs.seed_last_backup(setup.adopt(repo, passphrase))
                else:
                    setup.create(repo, passphrase or None)
                jobs.clear_error()  # a repository that opens (new or not): the failure of the one before no longer applies
            except DeltaError as err:
                if notes is not None:
                    notes.repository_failed(str(err))
                raise
            if created is not None:
                GLib.idle_add(created, repo)
            return True, ""

        self._submit(jobs, invocation, uuid.uuid4().hex, task)

    _submit = staticmethod(submit_job)

    def clear_previews(self) -> None:
        if self._preview is not None:
            self._preview.clear()

    def _clear_previews(self, invocation) -> None:
        self.clear_previews()
        invocation.return_value(None)

    def _list_snapshots_async(self, invocation) -> None:
        self._query_async(
            invocation, lambda: [snapshot_to_variant(s) for s in self._snapshots.list_snapshots()]
        )

    _query_async = staticmethod(run_query)

    def _on_get_property(self, connection, sender, object_path, interface_name, property_name):
        jobs = self._jobs
        if property_name == "Status":
            status = jobs.status if jobs else "idle"
            browsing = self._browse_control is not None and self._browse_control.is_open
            return GLib.Variant("s", "browsing" if status == "idle" and browsing else status)
        if property_name == "LastBackup":
            return GLib.Variant("t", jobs.last_backup if jobs else 0)
        if property_name == "NextBackup":
            return GLib.Variant("t", self._next_runs.value() if self._next_runs else 0)
        if property_name == "LastError":
            return GLib.Variant("s", jobs.last_error if jobs else "")
        if property_name == "UnavailableReason":
            return GLib.Variant("s", jobs.reason if jobs else "")
        if property_name == "CanMount":
            return GLib.Variant("b", self._browse is not None)
        return None
