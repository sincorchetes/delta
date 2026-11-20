"""Use case: keep the user informed of a backup's lifecycle."""

import logging
import time
from collections.abc import Callable

from delta.application.ports import Notifier
from delta.domain.errors import DestinationUnavailable
from delta.domain.notification import Notification, NotificationKind

log = logging.getLogger(__name__)

REMINDER_AFTER = 7 * 24 * 3600  # a drive that stays away is told once, and again after this long


class BackupNotifications:
    """Best effort: a notification problem must never affect a backup."""

    def __init__(self, notifier: Notifier, clock: Callable[[], float] = time.time) -> None:
        self._notifier = notifier
        self._clock = clock
        self._missing_told_at: float | None = None

    def started(self) -> None:
        self._send(NotificationKind.BACKUP_STARTED)

    def succeeded(self) -> None:
        self._missing_told_at = None
        self._send(NotificationKind.BACKUP_SUCCEEDED)

    def warned(self, detail: str) -> None:
        self._missing_told_at = None
        self._send(NotificationKind.BACKUP_WARNINGS, detail)

    def interrupted(self) -> None:
        self._send(NotificationKind.BACKUP_INTERRUPTED)

    def postponed(self) -> None:
        self._send(NotificationKind.BACKUP_POSTPONED)

    def failed(self, detail: str) -> None:
        self._send(NotificationKind.BACKUP_FAILED, detail)

    def destination_unavailable(self, error: DestinationUnavailable) -> None:
        """Once per absence of the drive, and a reminder after a week: the timer comes by every hour."""
        now = self._clock()
        if self._missing_told_at is not None and now - self._missing_told_at < REMINDER_AFTER:
            return
        self.destination_lost(error)

    def destination_lost(self, error: DestinationUnavailable) -> None:
        """The drive went while a backup ran: this replaces the "in progress" notification, so it is always sent."""
        self._missing_told_at = self._clock()
        self._send(NotificationKind.DESTINATION_UNAVAILABLE, error.hint)

    def repository_failed(self, detail: str) -> None:
        self._send(NotificationKind.REPOSITORY_FAILED, detail)

    def _send(self, kind: NotificationKind, detail: str = "") -> None:
        try:
            self._notifier.notify(Notification(kind, detail))
        except Exception:  # noqa: BLE001 - boundary: never break the backup
            log.exception("cannot send notification %s", kind.value)
