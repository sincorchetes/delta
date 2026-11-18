"""JobJournal adapter: a marker file under XDG_STATE_HOME."""

import os
from pathlib import Path

MARKER = "backup-in-progress"


def default_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(base) / "delta"


class FileJobJournal:
    def __init__(self, state_dir: Path | None = None) -> None:
        self._marker = (state_dir or default_state_dir()) / MARKER

    def begin(self) -> None:
        self._marker.parent.mkdir(parents=True, exist_ok=True)
        self._marker.touch()

    def end(self) -> None:
        self._marker.unlink(missing_ok=True)

    def was_interrupted(self) -> bool:
        return self._marker.exists()
