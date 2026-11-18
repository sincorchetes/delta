"""Use cases: restore a path from a snapshot, under a directory or beside the original."""

import filecmp
import functools
import os
import shutil
import tempfile
import uuid
from collections.abc import Callable
from datetime import datetime

from delta.application.ports import BackupEngine
from delta.application.snapshots import snapshot_name
from delta.domain.errors import DeltaError, InvalidPath, SnapshotNotFound
from delta.domain.paths import ensure_within, validate_in_home, validate_restore
from delta.domain.repository import Repository
from delta.i18n import _

SCRATCH_PREFIX = ".delta-restore-"
EXTRACT_CHUNK = 500  # paths per borg call: far below the argument-length limit, far fewer calls than one each

_same_bytes = functools.partial(filecmp.cmp, shallow=False)  # sizes first, so a different size costs nothing


def _is_folder(path: str) -> bool:
    """A real directory; a symlink to one is restored (and named) as a file."""
    return os.path.isdir(path) and not os.path.islink(path)


def _same_file(a: str, b: str) -> bool:
    """Two regular files with the same bytes. Folders and links are never "the same": they are
    always set aside, since comparing them would mean walking all of them."""
    if any(os.path.islink(p) or not os.path.isfile(p) for p in (a, b)):
        return False
    try:
        return _same_bytes(a, b)
    except OSError:
        return False


class RestoreService:
    """Extracts into `target` (recreating the original path), or beside the original."""

    def __init__(
        self,
        engine: BackupEngine,
        repo: Repository | None,
        home: str,
        resolve: Callable[[str], str] = os.path.realpath,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._engine = engine
        self._repo = repo
        self._home = home
        self._resolve = resolve
        self._clock = clock

    def prepare(self, source: str, target: str) -> tuple[str, str]:
        """Cheap synchronous validation; symlinks are resolved before the check."""
        source, target = validate_restore(source, target, self._home)
        real_target = ensure_within(self._resolve(target), self._resolve(self._home), "target")
        return source, real_target

    def prepare_in_place(self, source: str) -> str:
        """Validate a path to restore beside its original; its folder must stay in home."""
        source = validate_in_home(source, self._home)
        ensure_within(
            self._resolve(os.path.dirname(source)), self._resolve(self._home), "path"
        )
        return source

    @staticmethod
    def new_job_id() -> str:
        return uuid.uuid4().hex

    def restore(self, snapshot: str, source: str, target: str) -> None:
        if self._repo is None:
            raise DeltaError(_("no repository configured"))
        if not os.path.isdir(target):
            raise InvalidPath(_("target must be an existing directory"))
        name = snapshot_name(self._engine, self._repo, snapshot)
        self._engine.extract(self._repo, name, (source,), target)

    def restore_beside(self, snapshot: str, source: str, replace: bool) -> str:
        """Restore `source` next to the original and return where it ended up.

        Nothing is ever overwritten: a copy gets a fresh name, and replacing first
        moves the current version aside under a dated name. If the folder of the
        original was deleted too it is made again (inside the home folder only), which
        is what recovering something deleted needs.
        """
        if self._repo is None:
            raise DeltaError(_("no repository configured"))
        folder = self._resolve(os.path.dirname(source))
        name = snapshot_name(self._engine, self._repo, snapshot)
        made = self._recreate_folder(folder)
        try:
            return self._restore_into(self._repo, folder, name, source, replace)
        except BaseException:
            self._forget(made)  # a failed restore leaves no empty folders behind
            raise

    def _restore_into(self, repo: Repository, folder: str, name: str, source: str, replace: bool) -> str:
        try:
            scratch = tempfile.mkdtemp(prefix=SCRATCH_PREFIX, dir=folder)
        except OSError as err:
            raise DeltaError(_("cannot restore into {folder}: {reason}").format(folder=folder, reason=err.strerror)) from err
        try:
            self._engine.extract(repo, name, (source,), scratch)
            extracted = os.path.join(scratch, source.lstrip("/"))
            if not os.path.lexists(extracted):
                raise SnapshotNotFound(source)
            original = os.path.join(folder, os.path.basename(source))
            if replace:
                return self._replace(extracted, original)
            return self._place_copy(extracted, original)
        except OSError as err:
            raise DeltaError(str(err)) from err
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def place_missing(self, snapshot: str, sources: list[str]) -> list[str]:
        """Put back every path of `sources` that no longer exists, each under its own name.

        They are extracted together (a few hundred per borg call), not one call per path. This
        never overwrites: a path that exists by now is left alone. Folders that are gone are
        made again, inside the home folder only. Returns the paths put back; one the snapshot
        lacks is skipped.
        """
        if self._repo is None:
            raise DeltaError(_("no repository configured"))
        wanted = [self.prepare_in_place(path) for path in sources]
        name = snapshot_name(self._engine, self._repo, snapshot)
        todo = sorted(path for path in set(wanted) if not os.path.lexists(path))
        if not todo:
            return []
        try:
            scratch = tempfile.mkdtemp(prefix=SCRATCH_PREFIX, dir=self._resolve(self._home))
        except OSError as err:
            raise DeltaError(_("cannot restore: {reason}").format(reason=err.strerror)) from err
        try:
            for start in range(0, len(todo), EXTRACT_CHUNK):
                self._engine.extract(self._repo, name, tuple(todo[start : start + EXTRACT_CHUNK]), scratch)
            return [path for path in todo if self._put_back(scratch, path)]
        except OSError as err:
            raise DeltaError(str(err)) from err
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def _put_back(self, scratch: str, path: str) -> bool:
        extracted = os.path.join(scratch, path.lstrip("/"))
        if not os.path.lexists(extracted) or os.path.lexists(path):
            return False  # the snapshot lacks it, or something took its place meanwhile
        self._recreate_folder(self._resolve(os.path.dirname(path)))
        shutil.move(extracted, path)
        return True

    def _recreate_folder(self, folder: str) -> list[str]:
        """Make `folder` (already resolved) if it is gone, returning what was made, outermost first.

        The nearest folder that still exists must be inside the home folder: nothing outside it
        is ever created.
        """
        missing = []
        existing = folder
        while not os.path.isdir(existing):
            missing.append(existing)
            parent = os.path.dirname(existing)
            if parent == existing:
                break
            existing = parent
        ensure_within(existing, self._resolve(self._home), "path")
        made = []
        try:
            for path in reversed(missing):
                os.mkdir(path)
                made.append(path)
        except OSError as err:
            self._forget(made)
            raise DeltaError(_("cannot recreate {folder}: {reason}").format(folder=folder, reason=err.strerror)) from err
        return made

    @staticmethod
    def _forget(made: list[str]) -> None:
        for path in reversed(made):
            try:
                os.rmdir(path)  # only if empty: never removes anything that has content
            except OSError:
                pass

    def _place_copy(self, extracted: str, original: str) -> str:
        date = self._clock().strftime("%Y-%m-%d")
        label = _("{name} (restored {date})")
        destination = self._free_name(original, label, _is_folder(extracted), date=date)
        os.rename(extracted, destination)
        return destination

    def _replace(self, extracted: str, original: str) -> str:
        if os.path.lexists(original) and _same_file(extracted, original):
            return original  # already exactly this: nothing to put back, and nothing worth setting aside
        if os.path.lexists(original):
            stamp = self._clock().strftime("%Y-%m-%d %H-%M-%S")
            label = _("{name} (before restore {date})")
            kept = self._free_name(original, label, _is_folder(original), date=stamp)
            os.rename(original, kept)
            try:
                os.rename(extracted, original)
            except OSError:
                os.rename(kept, original)  # put the current version back
                raise
        else:
            os.rename(extracted, original)
        return original

    @staticmethod
    def _free_name(original: str, template: str, is_folder: bool, **fields: str) -> str:
        """A sibling name built from `template` that does not exist yet."""
        folder, base = os.path.split(original)
        stem, extension = (base, "") if is_folder else os.path.splitext(base)
        label = template.format(name=stem, **fields)
        candidate, number = os.path.join(folder, label + extension), 1
        while os.path.lexists(candidate):
            number += 1
            candidate = os.path.join(folder, f"{label} {number}{extension}")
        return candidate
