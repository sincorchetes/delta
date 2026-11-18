"""Use case: apply the retention policy to the repository."""

from delta.application.ports import BackupEngine
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy


class PruneService:
    def __init__(self, engine: BackupEngine, repo: Repository | None, policy: RetentionPolicy) -> None:
        self._engine = engine
        self._repo = repo
        self._policy = policy

    def run(self) -> bool:
        """Prune; returns False when there is nothing to do (no repo or empty policy)."""
        if self._repo is None or not self._policy.keeps_anything:
            return False
        self._engine.prune(self._repo, self._policy)
        return True
