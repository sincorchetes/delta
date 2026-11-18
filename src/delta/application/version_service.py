"""Use cases: the distinct versions a path has across snapshots, and what a folder held in one."""

from concurrent.futures import ThreadPoolExecutor

from delta.application.ports import VersionSource
from delta.application.snapshots import snapshot_name
from delta.domain.file_version import FileVersion, FolderEntry, distinct_versions
from delta.domain.paths import validate_in_home
from delta.domain.repository import Repository


SEARCH_LIMIT = 1000  # a search that matches more is too broad to read: ask for a longer word
PARALLEL_LISTINGS = 4  # borg processes at once when asking about every snapshot


class VersionService:
    def __init__(self, engine: VersionSource, repo: Repository | None, home: str) -> None:
        self._engine = engine
        self._repo = repo
        self._home = home

    def list_versions(self, path: str) -> list[FileVersion]:
        """Newest first; empty without a repository. Raises InvalidPath."""
        path = validate_in_home(path, self._home)
        if self._repo is None:
            return []
        snapshots = sorted(self._engine.list_snapshots(self._repo), key=lambda s: s.created)
        repo = self._repo
        # One borg call per snapshot, each ~0.3 s to open the repository: several at once (borg lets
        # readers share the repository), and `map` keeps the order, which `distinct_versions` needs.
        with ThreadPoolExecutor(max_workers=PARALLEL_LISTINGS) as pool:
            entries = list(pool.map(lambda s: self._engine.file_entry(repo, s.name, path), snapshots))
        found = [FileVersion(s, entry) for s, entry in zip(snapshots, entries) if entry is not None]
        return distinct_versions(found)

    def list_folder(self, snapshot: str, path: str) -> list[FolderEntry]:
        """What the folder held in `snapshot` (id or name); empty without a repository.

        Raises InvalidPath, or SnapshotNotFound when the snapshot is gone.
        """
        path = validate_in_home(path, self._home)
        if self._repo is None:
            return []
        return self._engine.list_folder(self._repo, snapshot_name(self._engine, self._repo, snapshot), path)

    def search_folder(self, snapshot: str, path: str, query: str) -> list[FolderEntry]:
        """Entries anywhere below the folder, as it was in `snapshot`, whose name has `query`.

        Empty for a blank query (listing everything is what `list_folder` is for). Names are
        relative to the folder. Raises InvalidPath, or SnapshotNotFound.
        """
        path = validate_in_home(path, self._home)
        if self._repo is None or not query.strip():
            return []
        name = snapshot_name(self._engine, self._repo, snapshot)
        return self._engine.search_folder(self._repo, name, path, query, SEARCH_LIMIT)
