"""D-Bus calls that start a path-based job (restore, preview) and the errors they answer with."""

import uuid

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

from delta.application.check_service import CheckService
from delta.application.deleted_service import DeletedService
from delta.application.preview_service import PreviewService
from delta.application.restore_service import RestoreService
from delta.application.unlock_service import UnlockService
from delta.daemon.job_runner import JobAlreadyRunning, JobRunner
from delta.domain.errors import BackupInterrupted, InvalidPath
from delta.i18n import _

ERROR_INVALID_ARGUMENT = "io.github.sincorchetes.Delta.Service1.Error.InvalidArgument"
ERROR_FAILED = "io.github.sincorchetes.Delta.Service1.Error.Failed"
ERROR_BUSY = "io.github.sincorchetes.Delta.Service1.Error.Busy"
ERROR_INVALID_PATH = "io.github.sincorchetes.Delta.Service1.Error.InvalidPath"
ERROR_UNAVAILABLE = "io.github.sincorchetes.Delta.Service1.Error.Unavailable"


def submit_job(
    jobs: JobRunner, invocation, job_id: str, task, records_backup: bool = False, checking: bool = False
) -> None:
    """Start `task` and reply with its job id, or with Busy if another job is running."""
    try:
        jobs.submit(job_id, task, records_backup, checking)
    except JobAlreadyRunning:
        invocation.return_dbus_error(ERROR_BUSY, _("another job is already running"))
        return
    invocation.return_value(GLib.Variant("(s)", (job_id,)))


def start_restore(jobs, restore: RestoreService | None, parameters, invocation) -> None:
    if jobs is None or restore is None:
        invocation.return_dbus_error(ERROR_UNAVAILABLE, _("restore is not available"))
        return
    snapshot_id, source, target = parameters.unpack()
    try:
        source, target = restore.prepare(source, target)
    except InvalidPath as err:
        invocation.return_dbus_error(ERROR_INVALID_PATH, str(err))
        return

    def task(on_progress):
        restore.restore(snapshot_id, source, target)
        return True, ""

    submit_job(jobs, invocation, restore.new_job_id(), task)


def start_restore_beside(jobs, restore: RestoreService | None, parameters, invocation, replace: bool) -> None:
    """The finished job's message is the path where the version was restored."""
    if jobs is None or restore is None:
        invocation.return_dbus_error(ERROR_UNAVAILABLE, _("restore is not available"))
        return
    snapshot_id, source = parameters.unpack()
    try:
        source = restore.prepare_in_place(source)
    except InvalidPath as err:
        invocation.return_dbus_error(ERROR_INVALID_PATH, str(err))
        return

    def task(on_progress):
        return True, restore.restore_beside(snapshot_id, source, replace)

    submit_job(jobs, invocation, restore.new_job_id(), task)


def start_restore_deleted(jobs, deleted: DeletedService | None, parameters, invocation) -> None:
    """Put back everything of a folder that is gone now. The finished job's message is how many
    items that was, as a decimal number."""
    if jobs is None or deleted is None:
        invocation.return_dbus_error(ERROR_UNAVAILABLE, _("restore is not available"))
        return
    snapshot_id, folder = parameters.unpack()
    try:
        folder = deleted.prepare(folder)
    except InvalidPath as err:
        invocation.return_dbus_error(ERROR_INVALID_PATH, str(err))
        return

    def task(on_progress):
        return True, str(deleted.restore(snapshot_id, folder))

    submit_job(jobs, invocation, uuid.uuid4().hex, task)


def start_preview(jobs, preview: PreviewService | None, parameters, invocation) -> None:
    """The finished job's message is the read-only path where the version was unpacked."""
    if jobs is None or preview is None:
        invocation.return_dbus_error(ERROR_UNAVAILABLE, _("previews are not available"))
        return
    snapshot_id, source = parameters.unpack()
    try:
        source = preview.prepare(source)
    except InvalidPath as err:
        invocation.return_dbus_error(ERROR_INVALID_PATH, str(err))
        return

    def task(on_progress):
        return True, preview.preview(snapshot_id, source)

    submit_job(jobs, invocation, uuid.uuid4().hex, task)


def start_unlock(jobs: JobRunner | None, unlock: UnlockService | None, invocation) -> None:
    """Only on the user's explicit request; a running job of ours makes this answer Busy."""
    if jobs is None or unlock is None:
        invocation.return_dbus_error(ERROR_UNAVAILABLE, _("unlocking is not available"))
        return

    def task(on_progress):
        if not unlock.run():
            return False, _("No backup repository is set up.")
        jobs.clear_error()
        return True, ""

    submit_job(jobs, invocation, uuid.uuid4().hex, task)


def start_check(jobs: JobRunner | None, check: CheckService | None, invocation) -> None:
    """Check that the repository can be read. The finished job's message says how it went, as a sentence."""
    if jobs is None or check is None:
        invocation.return_dbus_error(ERROR_UNAVAILABLE, _("checking the backups is not available"))
        return

    def task(on_progress):
        try:
            if not check.run():
                return False, _("No backup repository is set up.")
        except BackupInterrupted:
            return True, _("The check was cancelled.")
        return True, _("Your backups were checked and no problems were found.")

    submit_job(jobs, invocation, uuid.uuid4().hex, task, checking=True)


def cancel_check(jobs: JobRunner | None, interrupt, invocation) -> None:
    """Stops a check that is running; with nothing to cancel it does nothing (it never stops a backup)."""
    if jobs is not None and jobs.checking:
        interrupt()
    invocation.return_value(None)
