"""The next scheduled backup, cached so reading the D-Bus property never blocks the main loop."""

import threading
import time
from collections.abc import Callable

from delta.application.ports import Scheduler

MAX_AGE_SECONDS = 60.0


def _in_background(work: Callable[[], None]) -> None:
    threading.Thread(target=work, daemon=True).start()


class NextRunCache:
    """Returns the last known value at once and refreshes it in the background when stale."""

    def __init__(
        self,
        scheduler: Scheduler,
        max_age: float = MAX_AGE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        spawn: Callable[[Callable[[], None]], None] = _in_background,
    ) -> None:
        self._scheduler = scheduler
        self._max_age = max_age
        self._clock = clock
        self._spawn = spawn
        self._epoch = 0
        self._checked: float | None = None
        self._refreshing = False

    def value(self) -> int:
        """Epoch seconds of the next run; 0 while unknown."""
        stale = self._checked is None or self._clock() - self._checked >= self._max_age
        if stale and not self._refreshing:
            self._refreshing = True
            self._spawn(self._refresh)
        return self._epoch

    def _refresh(self) -> None:
        try:
            moment = self._scheduler.next_run()
            self._epoch = 0 if moment is None else int(moment.timestamp())
        except Exception:  # a broken scheduler must not take the daemon down
            self._epoch = 0
        finally:
            self._checked = self._clock()
            self._refreshing = False
