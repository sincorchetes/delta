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


def test_a_folder_that_cannot_be_read_is_available_for_the_engine_to_say(tmp_path, monkeypatch):
    def refuse(path):
        raise PermissionError(13, "Permission denied", path)

    monkeypatch.setattr(local_destination.os, "scandir", refuse)

    assert state(tmp_path) is DestinationState.AVAILABLE
    assert os.path.isdir(tmp_path)  # it is there: only listing it was refused


@pytest.mark.parametrize("name", ["a", ".hidden", "x y"])
def test_whatever_is_in_it_the_folder_is_not_empty(tmp_path, name):
    (tmp_path / name).mkdir()

    assert state(tmp_path) is DestinationState.AVAILABLE
