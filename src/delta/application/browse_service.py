"""Use case: open one snapshot as a read-only folder, and close it again."""

import os

from delta.application.ports import SnapshotMounter, SnapshotSource
from delta.application.snapshots import snapshot_name
from delta.domain.errors import DeltaError
from delta.domain.repository import Repository
from delta.i18n import _


class BrowseService:
    """One snapshot is open at a time, under `root` (private and volatile, like previews)."""

    def __init__(
        self, source: SnapshotSource, mounter: SnapshotMounter, repo: Repository | None, root: str
    ) -> None:
        self._source = source
        self._mounter = mounter
        self._repo = repo
        self._root = root
        self.is_open = False

    @property
    def mountpoint(self) -> str:
        return os.path.join(self._root, "snapshot")

    def open(self, snapshot: str) -> str:
        """Mount `snapshot` (an id or a name) and return the folder that shows it."""
        if self._repo is None:
            raise DeltaError(_("no repository configured"))
        name = snapshot_name(self._source, self._repo, snapshot)
        try:
            os.makedirs(self.mountpoint, mode=0o700, exist_ok=True)
        except OSError as err:
            raise DeltaError(_("cannot prepare the folder: {reason}").format(reason=err.strerror)) from err
        self._mounter.mount(self._repo, name, self.mountpoint)
        self.is_open = True
        return self.mountpoint

    def close(self) -> None:
        """Leave nothing mounted. Safe to call when nothing is open."""
        if not self.is_open:
            return
        self.is_open = False
        self._mounter.unmount(self.mountpoint)
