"""The place of the repository, looked at in a real folder."""

import os

import pytest

from delta.domain.destination import DestinationState
from delta.domain.repository import Repository
from delta.infrastructure import local_destination
from delta.infrastructure.local_destination import LocalDestination


def state(path):
    return LocalDestination().state(Repository(str(path)))


def test_a_folder_that_is_not_there_is_missing(tmp_path):
    assert state(tmp_path / "gone") is DestinationState.MISSING


def test_a_file_where_the_folder_should_be_is_missing_too(tmp_path):
    (tmp_path / "x").write_text("a file")

    assert state(tmp_path / "x") is DestinationState.MISSING


def test_a_link_to_what_is_gone_is_missing(tmp_path):
    (tmp_path / "link").symlink_to(tmp_path / "gone")

    assert state(tmp_path / "link") is DestinationState.MISSING


def test_an_empty_folder_is_empty_since_a_repository_never_is(tmp_path):
    # the mount point of a drive that is not mounted looks like this
    assert state(tmp_path) is DestinationState.EMPTY


def test_a_folder_with_something_in_it_is_available(tmp_path):
    (tmp_path / "config").write_text("[repository]")

    assert state(tmp_path) is DestinationState.AVAILABLE


def test_a_folder_that_may_not_be_listed_is_one_the_person_has_no_permission_for(tmp_path, monkeypatch):
    def refuse(path):
        raise PermissionError(13, "Permission denied", path)

    monkeypatch.setattr(local_destination.os, "scandir", refuse)

    assert state(tmp_path) is DestinationState.DENIED
    assert os.path.isdir(tmp_path)  # it is there: only listing it was refused


def test_a_folder_that_cannot_be_listed_for_another_reason_is_left_for_the_engine_to_say(tmp_path, monkeypatch):
    def fail(path):
        raise OSError(5, "Input/output error", path)

    monkeypatch.setattr(local_destination.os, "scandir", fail)

    assert state(tmp_path) is DestinationState.AVAILABLE


@pytest.mark.parametrize("name", ["a", ".hidden", "x y"])
def test_whatever_is_in_it_the_folder_is_not_empty(tmp_path, name):
    (tmp_path / name).mkdir()

    assert state(tmp_path) is DestinationState.AVAILABLE


# --- what the place says about itself: read-only, no permission, no room ----------------------------


class Usage:
    def __init__(self, free=10 * 1024 * 1024 * 1024, flag=0):
        self.f_bavail, self.f_frsize, self.f_flag = free // 4096, 4096, flag


def probed(tmp_path, free=10 * 1024 * 1024 * 1024, flag=0, access=True, out_of_space=False, statvfs=None):
    (tmp_path / "config").write_text("[repository]")
    destination = LocalDestination(statvfs or (lambda path: Usage(free, flag)), lambda path, mode: access)
    return destination.state(Repository(str(tmp_path)), out_of_space)


def test_a_place_with_room_that_can_be_written_is_available(tmp_path):
    assert probed(tmp_path) is DestinationState.AVAILABLE


def test_a_file_system_mounted_read_only_is_read_only(tmp_path):
    assert probed(tmp_path, flag=os.ST_RDONLY) is DestinationState.READ_ONLY


def test_read_only_is_said_before_denied_since_it_is_what_makes_it_unwritable(tmp_path):
    assert probed(tmp_path, flag=os.ST_RDONLY, access=False) is DestinationState.READ_ONLY


def test_a_folder_that_may_not_be_written_in_is_denied(tmp_path):
    assert probed(tmp_path, access=False) is DestinationState.DENIED


def test_what_is_asked_of_the_folder_is_to_write_and_to_enter_it(tmp_path):
    (tmp_path / "config").write_text("[repository]")
    asked = []

    def access(path, mode):
        asked.append((path, mode))
        return True

    LocalDestination(lambda path: Usage(), access).state(Repository(str(tmp_path)))

    assert asked == [(str(tmp_path), os.W_OK | os.X_OK)]


def test_a_place_with_less_than_a_mebibyte_is_full(tmp_path):
    assert probed(tmp_path, free=1024 * 1024 - 1) is DestinationState.FULL
    assert probed(tmp_path, free=1024 * 1024) is DestinationState.AVAILABLE


def test_a_place_short_of_room_is_the_one_that_ran_out_only_when_the_engine_says_a_disk_did(tmp_path):
    hundred_mebibytes = 100 * 1024 * 1024

    assert probed(tmp_path, free=hundred_mebibytes) is DestinationState.AVAILABLE
    assert probed(tmp_path, free=hundred_mebibytes, out_of_space=True) is DestinationState.FULL
    assert probed(tmp_path, free=256 * 1024 * 1024, out_of_space=True) is DestinationState.AVAILABLE  # the home folder, then


def test_a_place_whose_file_system_cannot_be_asked_is_judged_by_what_can_be_written(tmp_path):
    def fail(path):
        raise OSError(5, "Input/output error", path)

    assert probed(tmp_path, statvfs=fail) is DestinationState.AVAILABLE
    assert probed(tmp_path, statvfs=fail, access=False) is DestinationState.DENIED
