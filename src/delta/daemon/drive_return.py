"""When a drive is mounted, the backup that was waiting for it is made at once instead of at the next hour."""

from collections.abc import Callable


class DriveReturn:
    def __init__(self, status: Callable[[], str], start: Callable[[], object]) -> None:
        self._status, self._start = status, start

    def on_mounted(self) -> None:
        """Any mount may be the drive: if it is not, the try finds the place unreachable again and tells nothing new."""
        if self._status() == "unavailable":
            self._start()
