import os
from datetime import datetime

import pytest

from delta.application.browse_service import BrowseService
from delta.domain.errors import DeltaError, SnapshotNotFound
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot

REPO = Repository("/r")


class Source:
    def list_snapshots(self, repo):
        return [Snapshot("abc", "monday", datetime(2026, 1, 1))]


class Mounter:
    def __init__(self):
        self.calls = []

    def mount(self, repo, snapshot, mountpoint):
        self.calls.append(("mount", snapshot, mountpoint))

    def unmount(self, mountpoint):
        self.calls.append(("unmount", mountpoint))


@pytest.fixture
def world(tmp_path):
    mounter = Mounter()
    return mounter, BrowseService(Source(), mounter, REPO, str(tmp_path / "root")), str(tmp_path / "root" / "snapshot")


def test_opening_mounts_the_named_snapshot_in_a_private_folder(world):
    mounter, service, folder = world

    assert service.open("abc") == folder

    assert mounter.calls == [("mount", "monday", folder)]
    assert service.is_open
    assert oct(os.stat(folder).st_mode & 0o777) == "0o700"


def test_closing_unmounts_once_and_is_safe_to_repeat(world):
    mounter, service, folder = world
    service.open("monday")

    service.close()
    service.close()

    assert mounter.calls[1:] == [("unmount", folder)]
    assert not service.is_open


def test_closing_without_opening_does_nothing(world):
    mounter, service, _folder = world
    service.close()
    assert mounter.calls == []


def test_an_unknown_snapshot_is_not_mounted(world):
    mounter, service, _folder = world
    with pytest.raises(SnapshotNotFound):
        service.open("gone")
    assert mounter.calls == [] and not service.is_open


def test_without_a_repository_there_is_nothing_to_open(tmp_path):
    service = BrowseService(Source(), Mounter(), None, str(tmp_path))
    with pytest.raises(DeltaError, match="no repository"):
        service.open("abc")


def test_a_folder_that_cannot_be_made_is_a_clear_error(tmp_path):
    blocker = tmp_path / "root"
    blocker.write_text("a file, not a folder")
    mounter = Mounter()
    service = BrowseService(Source(), mounter, REPO, str(blocker))

    with pytest.raises(DeltaError, match="cannot prepare the folder"):
        service.open("abc")

    assert mounter.calls == []
