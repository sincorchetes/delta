"""Use case: unpack one old version into a read-only scratch folder so it can be looked at."""

import os
import shutil
import stat
import tempfile

from delta.application.ports import BackupEngine
from delta.application.snapshots import snapshot_name
from delta.domain.errors import DeltaError, SnapshotNotFound
from delta.domain.paths import validate_in_home
from delta.domain.repository import Repository
from delta.i18n import _

WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


def _make_read_only(top: str) -> None:
    """Nothing in a preview can be edited by mistake; the real file is never in danger anyway."""
    for folder, _dirs, files in os.walk(top):
        for name in files:
            path = os.path.join(folder, name)
            if not os.path.islink(path):
                os.chmod(path, os.stat(path).st_mode & ~WRITE_BITS)
        os.chmod(folder, os.stat(folder).st_mode & ~WRITE_BITS)


def _remove(path: str) -> None:
    for folder, _dirs, _files in os.walk(path):  # read-only folders cannot be emptied
        os.chmod(folder, 0o700)
    shutil.rmtree(path, ignore_errors=True)


class PreviewService:
    """Extracts a version under `root` (a private, volatile folder) and forgets it on request."""

    def __init__(self, engine: BackupEngine, repo: Repository | None, home: str, root: str) -> None:
        self._engine = engine
        self._repo = repo
        self._home = home
        self._root = root

    def prepare(self, source: str) -> str:
        """Cheap synchronous validation: only paths inside the home folder have versions."""
        return validate_in_home(source, self._home)

    def preview(self, snapshot: str, source: str) -> str:
        """Return where the version of `source` was unpacked (a file or a folder)."""
        if self._repo is None:
            raise DeltaError(_("no repository configured"))
        name = snapshot_name(self._engine, self._repo, snapshot)
        try:
            os.makedirs(self._root, mode=0o700, exist_ok=True)
            scratch = tempfile.mkdtemp(dir=self._root)
        except OSError as err:
            raise DeltaError(_("cannot prepare a preview: {reason}").format(reason=err.strerror)) from err
        try:
            self._engine.extract(self._repo, name, (source,), scratch)
            unpacked = os.path.join(scratch, source.lstrip("/"))
            if not os.path.lexists(unpacked):
                raise SnapshotNotFound(source)
            _make_read_only(scratch)
        except DeltaError:
            _remove(scratch)
            raise
        except OSError as err:
            _remove(scratch)
            raise DeltaError(str(err)) from err
        return unpacked

    def clear(self) -> None:
        """Forget every preview. Safe to call at any time, including when there are none."""
        try:
            entries = os.listdir(self._root)
        except OSError:
            return
        for entry in entries:
            _remove(os.path.join(self._root, entry))

