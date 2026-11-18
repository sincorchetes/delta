"""Gaps a mutation run found after M5 and M6: exact path refusals, disk-error reasons, the browse service."""

import errno
import os
import tempfile
from datetime import datetime

import pytest

from delta.application.browse_service import BrowseService
from delta.application.preview_service import PreviewService
from delta.application.restore_service import RestoreService
from delta.domain.errors import DeltaError, InvalidPath
from delta.domain.paths import ensure_within, validate_in_home, validate_restore
from delta.domain.repository import Repository
from delta.domain.snapshot import Snapshot

NOW = datetime(2026, 11, 10, 13, 5, 0)
REPO = Repository("/r")
HOME = "/home/user"
NO_SPACE = OSError(errno.ENOSPC, "No space left on device")


def refusal(call, *args):
    with pytest.raises(InvalidPath) as caught:
        call(*args)
    return str(caught.value)


# --- the words of each path refusal, per noun ------------------------------------------------------


def test_a_path_that_is_not_absolute_is_refused_by_the_noun_it_is():
    assert refusal(validate_in_home, "a.txt", HOME) == "path must be an absolute path"
    assert refusal(validate_restore, "a.txt", "/home/user/b", HOME) == "source must be an absolute path"
    assert refusal(validate_restore, "/home/user/a", "b", HOME) == "target must be an absolute path"


def test_a_path_with_a_parent_reference_is_refused_by_the_noun_it_is():
    assert refusal(validate_in_home, "/home/user/../x", HOME) == "path must not contain '..'"
    assert refusal(validate_restore, "/home/user/../x", "/home/user/b", HOME) == "source must not contain '..'"
    assert refusal(validate_restore, "/home/user/a", "/home/user/../x", HOME) == "target must not contain '..'"


def test_a_path_outside_the_base_is_refused_by_the_noun_it_is():
    assert refusal(validate_in_home, "/etc/x", HOME) == f"path must be inside {HOME}"
    assert refusal(validate_restore, "/etc/x", "/home/user/b", HOME) == f"source must be inside {HOME}"
    assert refusal(validate_restore, "/home/user/a", "/etc/x", HOME) == f"target must be inside {HOME}"
    assert refusal(ensure_within, "/etc/x", HOME, "path") == f"path must be inside {HOME}"


# --- the same, through the restore service, where the label is passed on -------------------------


class Engine:
    def list_snapshots(self, repo):
        return [Snapshot("id1", "first", NOW)]

    def extract(self, repo, snapshot, paths, destination):
        pass


@pytest.fixture
def home(tmp_path):
    root = tmp_path / "home"
    (root / "docs").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside)
    return root


def restorer(home):
    return RestoreService(Engine(), REPO, str(home), clock=lambda: NOW)


def test_a_folder_that_leads_out_of_home_is_refused_as_a_path_when_restoring_in_place(home):
    message = refusal(restorer(home).prepare_in_place, str(home / "link" / "a.txt"))

    assert message == f"path must be inside {os.path.realpath(home)}"


def test_a_folder_to_recreate_outside_home_is_refused_as_a_path(home):
    service = restorer(home)

    with pytest.raises(InvalidPath) as caught:
        service.restore_beside("first", str(home / "link" / "gone" / "a.txt"), replace=False)

    assert str(caught.value) == f"path must be inside {os.path.realpath(home)}"


# --- the reason a disk error gives is part of the message ---------------------------------------


def fail_with(error):
    def raiser(*_args, **_kwargs):
        raise error

    return raiser


def test_a_full_disk_says_why_when_a_preview_cannot_be_prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "mkdtemp", fail_with(NO_SPACE))
    service = PreviewService(Engine(), REPO, "/home/u", str(tmp_path / "preview"))

    with pytest.raises(DeltaError) as caught:
        service.preview("first", "/home/u/a.txt")

    assert str(caught.value) == "cannot prepare a preview: No space left on device"


def test_a_full_disk_says_where_and_why_when_restoring_beside(home, monkeypatch):
    monkeypatch.setattr(tempfile, "mkdtemp", fail_with(NO_SPACE))

    with pytest.raises(DeltaError) as caught:
        restorer(home).restore_beside("first", str(home / "docs" / "a.txt"), replace=False)

    folder = os.path.realpath(home / "docs")
    assert str(caught.value) == f"cannot restore into {folder}: No space left on device"


def test_a_full_disk_says_why_when_putting_back(home, monkeypatch):
    monkeypatch.setattr(tempfile, "mkdtemp", fail_with(NO_SPACE))

    with pytest.raises(DeltaError) as caught:
        restorer(home).place_missing("first", [str(home / "docs" / "a.txt")])

    assert str(caught.value) == "cannot restore: No space left on device"


def test_a_folder_that_cannot_be_recreated_says_which_and_why(home, monkeypatch):
    monkeypatch.setattr(os, "mkdir", fail_with(OSError(errno.EACCES, "Permission denied")))

    with pytest.raises(DeltaError) as caught:
        restorer(home).restore_beside("first", str(home / "docs" / "gone" / "a.txt"), replace=False)

    folder = os.path.realpath(home / "docs" / "gone")
    assert str(caught.value) == f"cannot recreate {folder}: Permission denied"


# --- the browse service --------------------------------------------------------------------------


class Source:
    def __init__(self):
        self.asked = []

    def list_snapshots(self, repo):
        self.asked.append(repo)
        return [Snapshot("abc", "monday", NOW)]


class Mounter:
    def __init__(self):
        self.mounted = []

    def mount(self, repo, snapshot, mountpoint):
        self.mounted.append((repo, snapshot))

    def unmount(self, mountpoint):
        pass


def browser(root, repo=REPO):
    source, mounter = Source(), Mounter()
    return source, mounter, BrowseService(source, mounter, repo, str(root))


def test_nothing_is_open_until_a_snapshot_is_opened_and_again_after_closing(tmp_path):
    _source, _mounter, service = browser(tmp_path / "root")
    assert service.is_open is False

    service.open("abc")
    assert service.is_open is True

    service.close()
    assert service.is_open is False


def test_the_repository_reaches_both_the_lookup_and_the_mount(tmp_path):
    source, mounter, service = browser(tmp_path / "root")

    service.open("abc")

    assert source.asked == [REPO]
    assert mounter.mounted == [(REPO, "monday")]


def test_a_folder_left_from_before_is_reused(tmp_path):
    _source, _mounter, service = browser(tmp_path / "root")
    os.makedirs(service.mountpoint)

    assert service.open("abc") == service.mountpoint


def test_without_a_repository_it_says_so(tmp_path):
    _source, _mounter, service = browser(tmp_path / "root", repo=None)

    with pytest.raises(DeltaError) as caught:
        service.open("abc")

    assert str(caught.value) == "no repository configured"


def test_a_folder_that_cannot_be_made_says_why(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where a folder should be")
    _source, _mounter, service = browser(blocker / "root")

    with pytest.raises(DeltaError) as caught:
        service.open("abc")

    assert str(caught.value) == "cannot prepare the folder: Not a directory"
