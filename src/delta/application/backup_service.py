"""Use case: run a backup job and track its outcome."""

import os
import uuid
from collections.abc import Callable

from delta.application.ports import BackupEngine
from delta.domain.backup_job import BackupJob
from delta.domain.errors import BackupInterrupted, BackupWarning, DeltaError
from delta.domain.progress import ProgressEvent
from delta.domain.repository import Repository
from delta.i18n import _


class BackupService:
    def __init__(
        self,
        engine: BackupEngine,
        repo: Repository | None,
        sources: tuple[str, ...],
        excludes: tuple[str, ...] = (),
    ) -> None:
        self._engine = engine
        self._repo = repo
        self._sources = sources
        self._excludes = excludes

    def new_job(self) -> BackupJob:
        """The repository is never part of what it holds: a destination inside the sources would copy itself."""
        own = () if self._repo is None else (f"pp:{os.path.normpath(self._repo.location)}",)
        return BackupJob(uuid.uuid4().hex, self._sources, self._excludes + own)

    def run(
        self, job: BackupJob, on_progress: Callable[[ProgressEvent], None] | None = None
    ) -> BackupJob:
        """Execute the job; failures are recorded on it, never raised."""
        if self._repo is None:
            job.fail(_("no repository configured"))
            return job
        job.start()
        try:
            self._engine.create(self._repo, job, on_progress=on_progress)
        except BackupInterrupted:
            job.interrupt()
        except BackupWarning as err:
            job.warn(str(err))
        except DeltaError as err:
            job.fail(str(err))
        else:
            job.succeed()
        return job
