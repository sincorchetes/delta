"""Use case: remove a stale lock from the repository, only on the user's explicit request."""

from delta.application.ports import BackupEngine
from delta.domain.repository import Repository


class UnlockService:
    def __init__(self, engine: BackupEngine, repo: Repository | None) -> None:
        self._engine = engine
        self._repo = repo

    def run(self) -> bool:
        """False when there is no repository to unlock."""
        if self._repo is None:
            return False
        self._engine.break_lock(self._repo)
        return True
