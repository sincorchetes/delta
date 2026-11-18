"""Use case: list the snapshots of the configured repository."""

from delta.application.ports import SnapshotSource
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot


def newest_timestamp(snapshots: list[Snapshot]) -> int:
    """Epoch seconds of the most recent snapshot; 0 when there is none."""
    return max((int(s.created.timestamp()) for s in snapshots), default=0)


class SnapshotService:
    def __init__(self, engine: SnapshotSource, repo: Repository | None) -> None:
        self._engine = engine
        self._repo = repo

    def list_snapshots(self) -> list[Snapshot]:
        """Newest first; empty when no repository is configured yet."""
        if self._repo is None:
            return []
        return sorted(self._engine.list_snapshots(self._repo), key=lambda s: s.created, reverse=True)

    def latest_backup(self) -> int:
        return newest_timestamp(self.list_snapshots())
