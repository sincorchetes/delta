"""The state of the place of the backups, known before a backup tries it and without blocking the main loop."""

import logging
import threading
import time
from collections.abc import Callable

from delta.application.ports import DestinationProbe
from delta.domain.destination import DestinationState
from delta.domain.repository import Repository

MAX_AGE_SECONDS = 10.0
log = logging.getLogger(__name__)


def _in_background(work: Callable[[], None]) -> None:
    threading.Thread(target=work, daemon=True).start()


class DestinationWatch:
    """Returns the last known state at once and asks the probe again in the background when it is stale or when told to.

    A drive that hangs while it is looked at holds up a thread, never the daemon.
    """

    def __init__(
        self,
        probe: DestinationProbe,
        repository: Callable[[], Repository | None],
        max_age: float = MAX_AGE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        spawn: Callable[[Callable[[], None]], None] = _in_background,
    ) -> None:
        self._probe = probe
        self._repository = repository
        self._max_age = max_age
        self._clock = clock
        self._spawn = spawn
        self._known = DestinationState.AVAILABLE
        self._checked: float | None = None
        self._refreshing = False

    def state(self) -> DestinationState:
        """AVAILABLE while nothing is known yet."""
        if self._checked is None or self._clock() - self._checked >= self._max_age:
            self.refresh()
        return self._known

    def refresh(self) -> None:
        """Look again now, off the main loop (a drive was mounted or taken away)."""
        if not self._refreshing:
            self._refreshing = True
            self._spawn(self._look)

    def _look(self) -> None:
        try:
            repo = self._repository()
            self._known = DestinationState.AVAILABLE if repo is None else self._probe.state(repo)
        except Exception as err:  # a probe that breaks must not take the daemon down: the next backup finds out
            log.warning("cannot look at the place of the backups: %s", err)
            self._known = DestinationState.AVAILABLE
        finally:
            self._checked = self._clock()
            self._refreshing = False
