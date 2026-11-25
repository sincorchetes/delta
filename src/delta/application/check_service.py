"""Use case: check that the repository can be read, only on the user's explicit request."""

from delta.application.ports import BackupEngine, DestinationProbe
from delta.domain.destination import DestinationState
from delta.domain.errors import DestinationUnavailable
from delta.domain.repository import Repository


class CheckService:
    def __init__(self, engine: BackupEngine, repo: Repository | None, destination: DestinationProbe) -> None:
        self._engine = engine
        self._repo = repo
        self._destination = destination

    def run(self) -> bool:
        """False when there is no repository to check. A place that cannot be used says why, as the engine would only fail on it;
        a repository with problems raises RepositoryDamaged."""
        if self._repo is None:
            return False
        state = self._destination.state(self._repo)
        if state is not DestinationState.AVAILABLE:
            raise DestinationUnavailable(self._repo.location, state)
        self._engine.check(self._repo)
        return True
