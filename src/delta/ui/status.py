"""What the status window says, decided from the daemon's state. No GTK, no D-Bus."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from delta.domain.errors import is_lock_message, is_missing_passphrase_message
from delta.i18n import _, ngettext


class Health(str, Enum):
    UNREACHABLE = "unreachable"
    NOT_CONFIGURED = "not-configured"
    RUNNING = "running"
    CHECKING = "checking"
    BROWSING = "browsing"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    LOCKED = "locked"
    NO_PASSPHRASE = "no-passphrase"
    PENDING = "pending"
    OK = "ok"


class Action(Enum):
    NONE = "none"  # no button
    BACK_UP = "back-up"
    SET_UP = "set-up"
    UNLOCK = "unlock"  # always behind an explicit confirmation
    ENTER_PASSPHRASE = "enter-passphrase"
    CANCEL_CHECK = "cancel-check"


@dataclass(frozen=True)
class DaemonSnapshot:
    reachable: bool = True
    status: str = "idle"
    last_backup: int = 0
    last_error: str = ""
    repository: str = ""
    schedule: str = "hourly"
    next_backup: int = 0  # epoch seconds; 0 = unknown
    reason: str = ""  # while the status is "unavailable": missing, empty, full, read-only or denied


@dataclass(frozen=True)
class StatusView:
    health: Health
    title: str
    subtitle: str
    icon_name: str
    action: Action = Action.NONE
    action_label: str = ""
    action_enabled: bool = True

    @property
    def can_back_up_now(self) -> bool:
        return self.action is Action.BACK_UP and self.action_enabled


MAX_ERROR = 240


def summarise(message: str) -> str:
    """One readable paragraph: newlines collapsed, long engine output cut short."""
    text = " ".join(message.split())
    return text if len(text) <= MAX_ERROR else text[:MAX_ERROR].rstrip() + "…"


def relative_time(epoch: int, now: datetime) -> str:
    seconds = max(0, int(now.timestamp()) - epoch)
    if seconds < 60:
        return _("just now")
    minutes = seconds // 60
    if minutes < 60:
        return ngettext("{n} minute ago", "{n} minutes ago", minutes).format(n=minutes)
    hours = minutes // 60
    if hours < 24:
        return ngettext("{n} hour ago", "{n} hours ago", hours).format(n=hours)
    days = hours // 24
    return ngettext("{n} day ago", "{n} days ago", days).format(n=days)


def until_time(epoch: int, now: datetime) -> str:
    """How far away a future moment is; an overdue one reads as imminent."""
    seconds = epoch - int(now.timestamp())
    if seconds < 60:
        return _("in a moment")
    minutes = seconds // 60
    if minutes < 60:
        return ngettext("in {n} minute", "in {n} minutes", minutes).format(n=minutes)
    hours = minutes // 60
    if hours < 24:
        return ngettext("in {n} hour", "in {n} hours", hours).format(n=hours)
    days = hours // 24
    return ngettext("in {n} day", "in {n} days", days).format(n=days)


def describe_schedule(expression: str) -> str:
    if expression == "hourly":
        return _("every hour")
    if expression == "daily":
        return _("every day")
    if expression == "weekly":
        return _("every week")
    return _("on the schedule “{expression}”").format(expression=expression)


def unavailable_view(snapshot: DaemonSnapshot) -> StatusView:
    """The place of the backups cannot be used, and each cause says what to do about it (none of them is a failed backup)."""
    where = snapshot.repository
    if snapshot.reason == "other-drive":
        title = _("Your backups are not on this drive")
        subtitle = _("A drive is connected at {location}, but it does not hold your backups. Connect the one that does, or choose another place in the preferences.")
        icon = "drive-harddisk-symbolic"
    elif snapshot.reason == "io-error":
        title = _("The drive with your backups reports errors")
        subtitle = _("{location} reported an error while it was written to. Check its connection; if it keeps happening, the drive may be failing.")
        icon = "dialog-warning-symbolic"
    elif snapshot.reason == "other-repository":
        title = _("These are not your backups")
        subtitle = _("The repository at {location} is not the one your backups were made in. Connect the drive that holds them. If this one is the right one, choose it again in the preferences, with its passphrase.")
        icon = "dialog-warning-symbolic"
    elif snapshot.reason == "full":
        title = _("The place with your backups is full")
        subtitle = _("There is no room left in {location}. Free some space, or choose another place in the preferences.")
        icon = "drive-harddisk-symbolic"
    elif snapshot.reason == "read-only":
        title = _("The place with your backups is read-only")
        subtitle = _("{location} is mounted so that nothing can be written to it. Mount it again for writing, or choose another place in the preferences. If this came after an error, the drive may be failing.")
        icon = "changes-prevent-symbolic"
    elif snapshot.reason == "denied":
        title = _("You cannot write where your backups are kept")
        subtitle = _("You do not have permission to write in {location}. Change its permissions, or choose another place in the preferences.")
        icon = "changes-prevent-symbolic"
    else:
        title = _("The drive with your backups is not connected")
        subtitle = _("Connect it to {location}. The next backup runs by itself when it is back.")
        icon = "drive-removable-media-symbolic"
    return StatusView(
        Health.UNAVAILABLE, title, subtitle.format(location=where), icon, Action.BACK_UP, _("Check again")
    )


def build_status(snapshot: DaemonSnapshot, now: datetime) -> StatusView:
    schedule = describe_schedule(snapshot.schedule)
    back_up = (Action.BACK_UP, _("Back up now"))
    if not snapshot.reachable:
        return StatusView(
            Health.UNREACHABLE,
            _("The backup service is not available"),
            _("Delta could not start its background service."),
            "dialog-warning-symbolic",
        )
    if not snapshot.repository:
        return StatusView(
            Health.NOT_CONFIGURED,
            _("Backups are not set up"),
            _("Choose where to keep your backups to get started."),
            "drive-harddisk-symbolic",
            Action.SET_UP,
            _("Set up backups"),
        )
    if snapshot.status == "running":
        return StatusView(
            Health.RUNNING,
            _("Backing up…"),
            _("Delta is backing up your files."),
            "view-refresh-symbolic",
            *back_up,
            action_enabled=False,
        )
    if snapshot.status == "checking":
        return StatusView(
            Health.CHECKING,
            _("Checking your backups…"),
            _("Delta is making sure your backups can be read. It may take a while; you can close this window."),
            "system-search-symbolic",
            Action.CANCEL_CHECK,
            _("Cancel"),
        )
    if snapshot.status == "browsing":
        return StatusView(
            Health.BROWSING,
            _("A backup is open as a folder"),
            _("The next copy starts when you close it."),
            "folder-symbolic",
            *back_up,
            action_enabled=False,
        )
    if snapshot.status == "unavailable":
        return unavailable_view(snapshot)
    if snapshot.last_error and is_lock_message(snapshot.last_error):
        return StatusView(
            Health.LOCKED,
            _("The backup repository is locked"),
            _("A backup did not finish cleanly, or something else is using the repository."),
            "dialog-warning-symbolic",
            Action.UNLOCK,
            _("Unlock…"),
        )
    if snapshot.last_error and is_missing_passphrase_message(snapshot.last_error):
        return StatusView(
            Health.NO_PASSPHRASE,
            _("The passphrase of your backups is not in the keyring"),
            _("Delta cannot open your backups without it, so nothing is backed up. Type it again and it is kept in the keyring."),
            "dialog-password-symbolic",
            Action.ENTER_PASSPHRASE,
            _("Enter passphrase…"),
        )
    if snapshot.last_error:
        return StatusView(
            Health.FAILED,
            _("The last backup failed"),
            summarise(snapshot.last_error),
            "dialog-error-symbolic",
            Action.BACK_UP,
            _("Try again"),
        )
    upcoming = until_time(snapshot.next_backup, now) if snapshot.next_backup else ""
    if snapshot.last_backup == 0:
        subtitle = (
            _("The first backup runs {when}.").format(when=upcoming)
            if upcoming
            else _("The first backup runs {schedule}.").format(schedule=schedule)
        )
        return StatusView(
            Health.PENDING, _("No backups yet"), subtitle, "appointment-soon-symbolic", *back_up
        )
    last = relative_time(snapshot.last_backup, now)
    subtitle = (
        _("Last backup: {when}. Next backup: {next}.").format(when=last, next=upcoming)
        if upcoming
        else _("Last backup: {when}. Backups run {schedule}.").format(when=last, schedule=schedule)
    )
    return StatusView(
        Health.OK, _("Your files are protected"), subtitle, "object-select-symbolic", *back_up
    )
