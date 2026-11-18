"""What the user is told about backups; wording is the adapter's concern."""

from dataclasses import dataclass
from enum import Enum


class NotificationKind(str, Enum):
    BACKUP_STARTED = "backup-started"
    BACKUP_SUCCEEDED = "backup-succeeded"
    BACKUP_WARNINGS = "backup-warnings"
    BACKUP_INTERRUPTED = "backup-interrupted"
    BACKUP_POSTPONED = "backup-postponed"
    BACKUP_FAILED = "backup-failed"
    REPOSITORY_FAILED = "repository-failed"


@dataclass(frozen=True)
class Notification:
    kind: NotificationKind
    detail: str = ""
