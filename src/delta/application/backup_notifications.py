"""Use case: keep the user informed of a backup's lifecycle."""

import logging

from delta.application.ports import Notifier
from delta.domain.errors import DestinationUnavailable
from delta.domain.notification import Notification, NotificationKind

log = logging.getLogger(__name__)


class BackupNotifications:
    """Best effort: a notification problem must never affect a backup."""

    def __init__(self, notifier: Notifier) -> None:
        self._notifier = notifier

    def started(self) -> None:
        self._send(NotificationKind.BACKUP_STARTED)

    def succeeded(self) -> None:
        self._send(NotificationKind.BACKUP_SUCCEEDED)

    def warned(self, detail: str) -> None:
        self._send(NotificationKind.BACKUP_WARNINGS, detail)

    def interrupted(self) -> None:
        self._send(NotificationKind.BACKUP_INTERRUPTED)

    def postponed(self) -> None:
        self._send(NotificationKind.BACKUP_POSTPONED)

    def failed(self, detail: str) -> None:
        self._send(NotificationKind.BACKUP_FAILED, detail)

    def destination_unavailable(self, error: DestinationUnavailable) -> None:
        self._send(NotificationKind.DESTINATION_UNAVAILABLE, error.hint)

    def repository_failed(self, detail: str) -> None:
        self._send(NotificationKind.REPOSITORY_FAILED, detail)

    def _send(self, kind: NotificationKind, detail: str = "") -> None:
        try:
            self._notifier.notify(Notification(kind, detail))
        except Exception:  # noqa: BLE001 - boundary: never break the backup
            log.exception("cannot send notification %s", kind.value)
