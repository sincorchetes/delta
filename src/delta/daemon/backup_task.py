"""The unit of work behind CreateBackup: backup, prune, journal and notifications."""

import logging
from collections.abc import Callable
from typing import cast

from delta.application.backup_notifications import BackupNotifications
from delta.application.backup_service import BackupService
from delta.application.ports import JobJournal
from delta.application.prune_service import PruneService
from delta.daemon.job_runner import Task
from delta.domain.backup_job import BackupJob, JobState
from delta.domain.errors import DeltaError, DestinationUnavailable
from delta.i18n import _

log = logging.getLogger(__name__)


def _journal(action: Callable[[], None]) -> None:
    """A journal problem must not stop a backup (it only weakens resume)."""
    try:
        action()
    except OSError as err:
        log.warning("cannot update the backup journal: %s", err)


def make_backup_task(
    job: BackupJob,
    backup: BackupService,
    prune: PruneService | None,
    notes: BackupNotifications | None,
    journal: JobJournal | None,
) -> Task:
    def task(on_progress) -> tuple[bool, str]:
        missing = backup.unreachable()
        if missing is not None:
            # Nothing was started, so there is nothing to withdraw and nothing to tell: the runner waits for the drive.
            job.wait_for_destination(missing)
            raise missing
        if journal is not None:
            _journal(journal.begin)
        if notes is not None:
            notes.started()
        backup.run(job, on_progress)

        if job.state is JobState.INTERRUPTED:
            # Keep the journal mark: the backup is resumed on the next start.
            if notes is not None:
                notes.interrupted()
            return False, _("interrupted; it will be resumed")
        if journal is not None:
            _journal(journal.end)

        if job.state is JobState.UNAVAILABLE:
            # The drive went while the engine worked: the notification of the start gives way to this one.
            error = cast(DestinationUnavailable, job.unavailable)
            if notes is not None:
                notes.destination_unavailable(error)
            raise error

        if job.state is JobState.FAILED:
            if notes is not None:
                notes.failed(job.message)
            return False, job.message
        message = job.message
        if prune is not None:
            try:
                prune.run()
            except DeltaError as err:
                message = _("backup done, prune failed: {error}").format(error=err)
        if notes is not None and message:
            notes.warned(message)
        elif notes is not None:
            notes.succeeded()
        return True, message

    return task
