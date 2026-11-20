"""The status window: what Delta is doing and a button to back up now."""

import os
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from delta.i18n import _
from delta.ui.a11y import tipped
from delta.ui.about import build_about
from delta.ui.client import DeltaClient
from delta.ui.history_window import HistoryWindow
from delta.ui.preferences_dialog import PreferencesDialog
from delta.ui.status import Action, DaemonSnapshot, Health, build_status, summarise
from delta.ui.wizard_window import SetupWizard

REFRESH_SECONDS = 30  # keeps "5 minutes ago" honest while the window stays open


class StatusWindow(Adw.ApplicationWindow):
    def __init__(self, application, client: DeltaClient, settings) -> None:
        super().__init__(
            application=application, title=_("Delta"), default_width=640, default_height=720
        )
        self._client, self._settings = client, settings
        self._health = Health.UNREACHABLE
        self._action = Action.NONE

        self._page = Adw.StatusPage()
        self._page.add_css_class("compact")  # a smaller title, so long ones are not clipped
        self._button = Gtk.Button(halign=Gtk.Align.CENTER)
        self._button.add_css_class("pill")
        self._button.add_css_class("suggested-action")
        self._button.connect("clicked", self._on_back_up_clicked)
        self._page.set_child(self._button)

        self._toasts = Adw.ToastOverlay()
        self._toasts.set_child(self._page)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self._history = tipped(Gtk.Button(icon_name="document-open-recent-symbolic"), _("Backup history"))
        self._history.set_sensitive(False)
        self._history.connect("clicked", lambda button: HistoryWindow(self, client).present())
        header.pack_start(self._history)
        menu = Gio.Menu()
        menu.append(_("Preferences"), "win.preferences")
        menu.append(_("Help"), "app.help")
        menu.append(_("About Delta"), "win.about")
        header.pack_end(
            tipped(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu), _("Main menu"))
        )
        preferences = Gio.SimpleAction.new("preferences", None)
        preferences.set_enabled(settings is not None)
        preferences.connect("activate", self._on_preferences)
        self.add_action(preferences)
        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", lambda action, parameter: build_about().present(self))
        self.add_action(about)
        application.set_accels_for_action("win.preferences", ["<Control>comma"])
        toolbar.add_top_bar(header)
        toolbar.set_content(self._toasts)
        self.set_content(toolbar)

        self._subscriptions = [
            client.on_backup_finished(self._on_finished),
            client.on_progress(self._on_progress),
        ]
        if settings is not None:
            settings.connect("changed", lambda *args: self.refresh())
        self._timer = GLib.timeout_add_seconds(REFRESH_SECONDS, self._on_tick)
        self.connect("close-request", self._on_close)
        self.refresh()

    def refresh(self) -> None:
        self._client.read_state(self._on_state)

    def _on_state(self, properties, error) -> None:
        props = properties or {}
        snapshot = DaemonSnapshot(
            reachable=error is None,
            status=props.get("Status", "idle"),
            last_backup=props.get("LastBackup", 0),
            next_backup=props.get("NextBackup", 0),
            last_error=props.get("LastError", ""),
            repository=self._setting("repository-location", ""),
            schedule=self._setting("schedule", "hourly"),
        )
        view = build_status(snapshot, datetime.now())
        self._health = view.health
        self._page.set_icon_name(view.icon_name)
        self._page.set_title(view.title)
        self._page.set_description(GLib.markup_escape_text(view.subtitle))
        self._action = view.action
        self._history.set_sensitive(view.health not in (Health.NOT_CONFIGURED, Health.UNREACHABLE))
        self._button.set_label(view.action_label)
        self._button.set_sensitive(view.action_enabled)
        self._button.set_visible(view.action is not Action.NONE)

    def _setting(self, key: str, default: str) -> str:
        return self._settings.get_string(key) if self._settings is not None else default

    def _on_back_up_clicked(self, button) -> None:
        if self._action is Action.SET_UP:
            SetupWizard(self, self._client, self._settings, self.refresh).present()
            return
        if self._action is Action.UNLOCK:
            self._confirm_unlock()
            return
        button.set_sensitive(False)
        self._client.create_backup(self._on_started)

    def _on_preferences(self, action, parameter) -> None:
        if self._settings is not None:
            PreferencesDialog(self._settings, os.path.expanduser("~"), self, self._client).present(self)

    def _confirm_unlock(self) -> None:
        """Breaking a lock that is really held can damage the backups, so the user must say yes."""
        dialog = Adw.AlertDialog.new(
            _("Unlock the repository?"),
            _(
                "Only continue if no backup is running right now, on this computer or on any "
                "other that uses this repository. Unlocking one that is in use can damage your backups."
            ),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("unlock", _("Unlock"))
        dialog.set_response_appearance("unlock", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.choose(self, None, self._on_unlock_answer)

    def _on_unlock_answer(self, dialog, result) -> None:
        if dialog.choose_finish(result) == "unlock":
            self._button.set_sensitive(False)
            self._client.unlock_repository(self._on_started)

    def _on_started(self, job_id, error) -> None:
        if error:
            self._toast(error)
        self.refresh()

    def _on_finished(self, job_id: str, ok: bool, message: str) -> None:
        if not ok and message:
            self._toast(message)
        self.refresh()

    def _on_progress(self, job_id: str, percent: float, path: str) -> None:
        if self._health is not Health.RUNNING:
            self.refresh()

    def _on_tick(self) -> bool:
        self.refresh()
        return GLib.SOURCE_CONTINUE

    def _on_close(self, window) -> bool:
        GLib.source_remove(self._timer)
        for subscription in self._subscriptions:
            self._client.unsubscribe(subscription)
        return False

    def _toast(self, message: str) -> None:
        self._toasts.add_toast(Adw.Toast.new(GLib.markup_escape_text(summarise(message))))
