"""Use case: keep the user informed of a backup's lifecycle."""

import logging
import time
from collections.abc import Callable

from delta.application.ports import Notifier
from delta.domain.destination import DestinationState
from delta.domain.errors import DestinationUnavailable
from delta.domain.notification import Notification, NotificationKind

log = logging.getLogger(__name__)

REMINDER_AFTER = 7 * 24 * 3600  # a place that stays unusable is told once, and again after this long
DESTINATION_KINDS = {
    DestinationState.MISSING: NotificationKind.DESTINATION_UNAVAILABLE,
    DestinationState.EMPTY: NotificationKind.DESTINATION_UNAVAILABLE,
    DestinationState.OTHER_DRIVE: NotificationKind.DESTINATION_OTHER_DRIVE,
    DestinationState.OTHER_REPOSITORY: NotificationKind.DESTINATION_OTHER_REPOSITORY,
    DestinationState.FULL: NotificationKind.DESTINATION_FULL,
    DestinationState.READ_ONLY: NotificationKind.DESTINATION_READ_ONLY,
    DestinationState.DENIED: NotificationKind.DESTINATION_DENIED,
}


class BackupNotifications:
    """Best effort: a notification problem must never affect a backup."""

    def __init__(self, notifier: Notifier, clock: Callable[[], float] = time.time) -> None:
        self._notifier = notifier
        self._clock = clock
        self._told: tuple[DestinationState, float] | None = None  # the cause of the last notice about the place, and when

    def started(self) -> None:
        self._send(NotificationKind.BACKUP_STARTED)

    def succeeded(self) -> None:
        self._told = None
        self._send(NotificationKind.BACKUP_SUCCEEDED)

    def warned(self, detail: str) -> None:
        self._told = None
        self._send(NotificationKind.BACKUP_WARNINGS, detail)

    def interrupted(self) -> None:
        self._send(NotificationKind.BACKUP_INTERRUPTED)

    def postponed(self) -> None:
        self._send(NotificationKind.BACKUP_POSTPONED)

    def failed(self, detail: str) -> None:
        self._send(NotificationKind.BACKUP_FAILED, detail)

    def destination_unavailable(self, error: DestinationUnavailable) -> None:
        """Once for each cause, and a reminder after a week: the timer comes by every hour. Another cause is news."""
        now = self._clock()
        if self._told is not None and self._told[0] is error.state and now - self._told[1] < REMINDER_AFTER:
            return
        self.destination_lost(error)

    def destination_lost(self, error: DestinationUnavailable) -> None:
        """The place went while a backup ran: this replaces the "in progress" notification, so it is always sent."""
        self._told = (error.state, self._clock())
        self._send(DESTINATION_KINDS[error.state], error.hint)

    def repository_failed(self, detail: str) -> None:
        self._send(NotificationKind.REPOSITORY_FAILED, detail)

    def _send(self, kind: NotificationKind, detail: str = "") -> None:
        try:
            self._notifier.notify(Notification(kind, detail))
        except Exception:  # noqa: BLE001 - boundary: never break the backup
            log.exception("cannot send notification %s", kind.value)
