"""Use case: remove a stale lock from the repository, only on the user's explicit request."""

from delta.application.ports import BackupEngine, DestinationProbe
from delta.domain.destination import DestinationState
from delta.domain.errors import DestinationUnavailable
from delta.domain.repository import Repository


class UnlockService:
    def __init__(self, engine: BackupEngine, repo: Repository | None, destination: DestinationProbe) -> None:
        self._engine = engine
        self._repo = repo
        self._destination = destination

    def run(self) -> bool:
        """False when there is no repository to unlock. A place that cannot be used says why, instead of the engine's own words:
        the lock that the window still shows may be an old one, and the drive may be gone since."""
        if self._repo is None:
            return False
        state = self._destination.state(self._repo)
        if state is not DestinationState.AVAILABLE:
            raise DestinationUnavailable(self._repo.location, state)
        self._engine.break_lock(self._repo)
        return True
