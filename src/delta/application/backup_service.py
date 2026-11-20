"""Use case: run a backup job and track its outcome."""

import os
import uuid
from collections.abc import Callable

from delta.application.ports import BackupEngine, DestinationProbe, RepositoryIdentity
from delta.domain.backup_job import BackupJob
from delta.domain.destination import DestinationState
from delta.domain.errors import BackupInterrupted, BackupWarning, DeltaError, DestinationUnavailable, is_full_message
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
        destination: DestinationProbe | None = None,
        identity: RepositoryIdentity | None = None,
    ) -> None:
        self._engine = engine
        self._repo = repo
        self._sources = sources
        self._excludes = excludes
        self._destination = destination
        self._identity = identity

    def new_job(self) -> BackupJob:
        """The repository is never part of what it holds: a destination inside the sources would copy itself."""
        own = () if self._repo is None else (f"pp:{os.path.normpath(self._repo.location)}",)
        return BackupJob(uuid.uuid4().hex, self._sources, self._excludes + own)

    def run(
        self, job: BackupJob, on_progress: Callable[[ProgressEvent], None] | None = None, checked: bool = False
    ) -> BackupJob:
        """Execute the job; failures are recorded on it, never raised. `checked`: the caller has just asked `cannot_back_up`."""
        if self._repo is None:
            job.fail(_("no repository configured"))
            return job
        missing = None if checked else self.cannot_back_up()
        if missing is not None:  # a drive that is not connected: there is nothing to ask the engine, and it is not a failure
            job.wait_for_destination(missing)
            return job
        job.start()
        try:
            self._engine.create(self._repo, job, on_progress=on_progress)
        except BackupInterrupted:
            job.interrupt()
        except BackupWarning as err:
            job.warn(str(err))
        except DeltaError as err:
            missing = self.unreachable(is_full_message(str(err)))  # the drive may have gone or filled up: not its failure either
            if missing is not None:
                job.wait_for_destination(missing)
            else:
                job.fail(str(err))
        else:
            job.succeed()
        return job

    def cannot_back_up(self) -> DestinationUnavailable | None:
        """Why the backup has to wait: the place cannot be used, or another repository is in it."""
        return self.unreachable() or self._replaced()

    def _replaced(self) -> DestinationUnavailable | None:
        """Another repository where the one Delta made was. The first time there is nothing to compare with: it is learnt."""
        if self._identity is None or self._repo is None:
            return None
        try:
            found = self._engine.repository_id(self._repo)
        except DeltaError:
            return None  # the engine says what is wrong (a passphrase, a lock) when the backup asks it for more
        expected = self._identity.expected()
        if not expected:
            self._identity.remember(found)
            return None
        if found != expected:
            return DestinationUnavailable(self._repo.location, DestinationState.OTHER_REPOSITORY)
        return None

    def unreachable(self, out_of_space: bool = False) -> DestinationUnavailable | None:
        """The error to wait with when the place of the repository cannot be used, else None."""
        if self._destination is None or self._repo is None:
            return None
        state = self._destination.state(self._repo, out_of_space)
        if state is DestinationState.AVAILABLE:
            return None
        return DestinationUnavailable(self._repo.location, state)
