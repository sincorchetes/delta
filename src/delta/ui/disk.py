"""The real filesystem behind the wizard's `Inspect` hook."""

import os

from delta.ui.wizard import PathState


def inspect_path(path: str) -> PathState:
    if not os.path.lexists(path):
        return PathState.MISSING
    if not os.path.isdir(path):
        return PathState.FILE
    try:
        with os.scandir(path) as entries:
            return PathState.NOT_EMPTY if any(True for _entry in entries) else PathState.EMPTY_DIR
    except OSError:
        return PathState.NOT_EMPTY  # unreadable: certainly not a place to create a repository
