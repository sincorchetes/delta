"""Notifier adapter over Gio.Notification (GNOME Shell / Flatpak portal)."""

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from delta.domain.notification import Notification, NotificationKind
from delta.i18n import _

# One id: "in progress" is replaced in place by the final result.
NOTIFICATION_ID = "backup"
OPEN_ACTION = "open-ui"
ICON = "drive-harddisk-symbolic"
MAX_DETAIL = 300


def render(notification: Notification) -> tuple[str, str, Gio.NotificationPriority]:
    """Title, body and priority for a notification."""
    detail = notification.detail.strip()
    if len(detail) > MAX_DETAIL:
        detail = detail[:MAX_DETAIL].rstrip() + "…"
    kind = notification.kind
    if kind is NotificationKind.BACKUP_STARTED:
        return _("Backup in progress"), _("Delta is backing up your files."), Gio.NotificationPriority.LOW
    if kind is NotificationKind.BACKUP_SUCCEEDED:
        return _("Backup complete"), _("Your files are safely backed up."), Gio.NotificationPriority.LOW
    if kind is NotificationKind.BACKUP_WARNINGS:
        body = detail or _("Some files could not be backed up.")
        return _("Backup complete with warnings"), body, Gio.NotificationPriority.NORMAL
    if kind is NotificationKind.BACKUP_INTERRUPTED:
        return (
            _("Backup interrupted"),
            _("Delta will resume it automatically."),
            Gio.NotificationPriority.NORMAL,
        )
    if kind is NotificationKind.BACKUP_POSTPONED:
        return (
            _("Backup postponed"),
            _("A backup is open as a folder. The new copy will start when you close it."),
            Gio.NotificationPriority.NORMAL,
        )
    if kind is NotificationKind.REPOSITORY_FAILED:
        body = detail or _("The backup destination could not be created.")
        return _("Could not set up backups"), body, Gio.NotificationPriority.HIGH
    body = detail or _("The backup could not be completed.")
    return _("Backup failed"), body, Gio.NotificationPriority.HIGH


class GioNotifier:
    def __init__(
        self, application: Gio.Application, open_ui: Callable[[], None] | None = None
    ) -> None:
        """With `open_ui`, clicking a notification opens the app (the shell calls this action)."""
        self._application = application
        self._opens_ui = open_ui is not None
        if open_ui is not None:
            action = Gio.SimpleAction.new(OPEN_ACTION, None)
            action.connect("activate", lambda action, parameter: open_ui())
            application.add_action(action)

    def notify(self, notification: Notification) -> None:
        """Safe from any thread: delivery happens on the main loop."""
        GLib.idle_add(self._send, *render(notification))

    def _send(self, title: str, body: str, priority: Gio.NotificationPriority) -> bool:
        message = Gio.Notification.new(title)
        message.set_body(body)
        message.set_priority(priority)
        message.set_icon(Gio.ThemedIcon.new(ICON))
        if self._opens_ui:
            message.set_default_action(f"app.{OPEN_ACTION}")
        self._application.send_notification(NOTIFICATION_ID, message)
        return False
