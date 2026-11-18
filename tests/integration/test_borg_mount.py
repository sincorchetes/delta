"""A snapshot opened as a folder with the real borg and FUSE, and closed again with a file still open."""

import os
import shutil

import pytest

from delta.application.backup_service import BackupService
from delta.domain.repository import Repository
from delta.infrastructure.borg_mounter import BorgMounter
from delta.infrastructure.borg_runner import BorgRunner

pytestmark = pytest.mark.skipif(
    shutil.which("borg") is None or shutil.which("fusermount3") is None or not os.path.exists("/dev/fuse"),
    reason="borg or FUSE not available",
)


@pytest.fixture
def world(tmp_path):
    runner = BorgRunner(env={"BORG_PASSPHRASE": "x", "BORG_BASE_DIR": str(tmp_path / "bh")})
    repo = Repository(str(tmp_path / "repo"))
    runner.init(repo)
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.txt").write_text("v1")
    snapshot = runner.create(repo, BackupService(runner, repo, (str(data),)).new_job())
    folder = tmp_path / "mnt"
    folder.mkdir()
    return runner, repo, snapshot, str(folder), str(data)


def test_a_snapshot_is_readable_as_a_folder_and_closes_even_with_a_file_open(world):
    runner, repo, snapshot, folder, data = world
    mounter = BorgMounter(runner)

    mounter.mount(repo, snapshot, folder)
    assert os.path.ismount(folder)
    held = open(os.path.join(folder, data.lstrip("/"), "a.txt"))
    assert held.read() == "v1"

    mounter.unmount(folder)

    assert not os.path.ismount(folder)
    with pytest.raises(OSError):  # the program that held it loses the file, as intended
        held.close()


def test_the_repository_is_free_again_once_the_snapshot_is_closed(world):
    runner, repo, snapshot, folder, data = world
    mounter = BorgMounter(runner)
    mounter.mount(repo, snapshot, folder)
    mounter.unmount(folder)

    runner.create(repo, BackupService(runner, repo, (data,)).new_job(), "after")

    assert "after" in [s.name for s in runner.list_snapshots(repo)]
