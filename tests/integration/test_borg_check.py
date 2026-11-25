"""A real Borg checks a real repository: a sound one passes, one with a damaged segment is told as damaged."""

import os
import shutil

import pytest

from delta.domain.backup_job import BackupJob
from delta.domain.errors import RepositoryDamaged
from delta.domain.repository import Repository
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(shutil.which("borg") is None, reason="borg not installed")


class MemoryStore:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, secret):
        self.data[key] = secret

    def delete(self, key):
        self.data.pop(key, None)


@pytest.fixture
def made(tmp_path):
    """A runner and a repository that holds one backup of a megabyte of data."""
    store = MemoryStore()
    runner = BorgRunner(env={"BORG_BASE_DIR": str(tmp_path / "home")}, secrets=store)
    repo = Repository(str(tmp_path / "repo"))
    store.data[repo.location] = "pw"
    source = tmp_path / "data"
    source.mkdir()
    (source / "big.bin").write_bytes(os.urandom(1024 * 1024))
    runner.init(repo)
    runner.create(repo, BackupJob("job", (str(source),)))
    return runner, repo, tmp_path / "repo"


def test_a_sound_repository_passes_the_check(made):
    runner, repo, _folder = made

    runner.check(repo)


def test_a_repository_with_a_damaged_segment_is_told_as_damaged(made):
    runner, repo, folder = made
    segment = max((path for path in (folder / "data").rglob("*") if path.is_file()), key=lambda path: path.stat().st_size)
    damaged = bytearray(segment.read_bytes())
    middle = len(damaged) // 2
    damaged[middle : middle + 64] = bytes(byte ^ 0xFF for byte in damaged[middle : middle + 64])
    segment.write_bytes(bytes(damaged))

    with pytest.raises(RepositoryDamaged):
        runner.check(repo)
