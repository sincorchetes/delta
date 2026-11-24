"""Where the folder chooser opens: the nearest folder that exists on the way to what was typed."""

import pytest

from delta.ui.wizard import PathState, WizardModel

HOME = "/home/u"
EXISTING = {"/home/u", "/home/u/Backups", "/media/disk"}


def inspect(path):
    return PathState.NOT_EMPTY if path in EXISTING else PathState.FILE if path == "/home/u/notes.txt" else PathState.MISSING


@pytest.mark.parametrize(
    "typed, start",
    [
        ("~/Backups", "/home/u/Backups"),
        ("~/Backups/new/deeper", "/home/u/Backups"),
        ("/media/disk/delta-backups", "/media/disk"),
        ("  ~/Backups/new  ", "/home/u/Backups"),
        ("~/notes.txt", "/home/u"),
        ("~", "/home/u"),
        ("/nowhere/at/all", ""),
        ("/", ""),
        ("", ""),
        ("relative/path", ""),
    ],
)
def test_the_chooser_opens_in_the_nearest_folder_that_exists(typed, start):
    assert WizardModel(home=HOME, inspect=inspect, destination=typed).chooser_start() == start
