"""Where the desktop mounts drives: a place there is on a drive that is mounted or away; anywhere else is the computer's disk."""

import pytest

from delta.infrastructure.drive_mounts import drive_mounted


def never(path):
    return False


def mounted(*points):
    return lambda path: path in points


@pytest.mark.parametrize("path", ["/run/media/u/DISK/delta", "/media/DISK", "/media/u/DISK/a/b", "/run/media/u"])
def test_a_place_in_the_mounts_with_nothing_mounted_is_a_drive_that_is_away(path):
    assert drive_mounted(path, never) is False


@pytest.mark.parametrize(
    "path, point",
    [
        ("/run/media/u/DISK/delta", "/run/media/u/DISK"),
        ("/media/DISK", "/media/DISK"),
        ("/media/u/DISK/a/b", "/media/u/DISK"),
    ],
)
def test_on_a_mount_the_drive_is_there_whatever_the_depth(path, point):
    assert drive_mounted(path, mounted(point)) is True


@pytest.mark.parametrize("path", ["/home/u/Backups", "/mnt/backups", "/media", "/run/media", "/tmp/x"])
def test_anywhere_else_it_is_not_a_question_of_drives(path):
    assert drive_mounted(path, never) is None
