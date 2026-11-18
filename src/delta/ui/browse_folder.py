"""«Browse as a folder»: open the chosen backup read-only in Files, and close it when done.

Only where the daemon can mount backups (the Flatpak install cannot): the button stays hidden
otherwise. The window that opened the folder keeps it open, and closes it with itself.
"""

import os
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from delta.i18n import _
from delta.ui.client import DeltaClient
from delta.ui.job_tracker import JobTracker
from delta.ui.status import summarise
from delta.ui.version_preview import Target


class BrowseFolder:
    def __init__(
        self,
        client: DeltaClient,
        tracker: JobTracker,
        toast: Callable[[str], None],
        on_change: Callable[[], None],
        show: Callable[[str], None],
    ) -> None:
        self._client, self._tracker, self._toast = client, tracker, toast
        self._on_change, self._show = on_change, show
        self._opened = False
        self._state = "closed"
        self.button = Gtk.Button(label=_("Browse as a folder"), visible=False)
        self.button.connect("clicked", self._on_clicked)
        self._target: Target | None = None
        self._subscription = client.on_snapshot_closed(self._on_closed)
        client.read_state(self._on_state)

    def _on_state(self, state, error) -> None:
        self.button.set_visible(error is None and bool(state.get("CanMount")))

    def sync(self, target: Target | None) -> None:
        """Called whenever the window's state changes: what the button says and whether it works."""
        self._target = target
        labels = {
            "closed": _("Browse as a folder"),
            "opening": _("Preparing the backup…"),
            "open": _("Close the folder"),
            "closing": _("Closing…"),
        }
        self.button.set_label(labels[self._state])
        self.button.set_sensitive(not self._tracker.busy and (self._opened or target is not None))

    def _on_clicked(self, button) -> None:
        if self._tracker.busy:
            return
        if self._opened:
            self._set("closing")
            self._tracker.begin(self._closed)
            self._client.unmount_snapshot(self._tracker.on_started)
        elif self._target is not None:
            target = self._target
            self._set("opening")
            self._tracker.begin(lambda ok, message: self._open_done(target, ok, message))
            self._client.mount_snapshot(target.snapshot, self._tracker.on_started)

    def _open_done(self, target: Target, ok: bool, message: str) -> None:
        self._opened = ok
        self._set("open" if ok else "closed")
        if ok:
            self._show(os.path.join(message, target.path.lstrip("/")))
        else:
            self._toast(summarise(message))

    def _closed(self, ok: bool, message: str) -> None:
        self._opened = False
        self._set("closed")

    def _on_closed(self, reason: str) -> None:
        """The daemon closed it (sleep, lock, the window gone...). Our own request is handled above."""
        if not self._opened or self._state == "closing":
            return
        self._opened = False
        self._set("closed")
        self._toast(_("The backup folder was closed."))

    def _set(self, state: str) -> None:
        self._state = state
        self._on_change()

    def close(self) -> None:
        """With the window: nothing should stay open that nobody can close any more."""
        self._client.unsubscribe(self._subscription)
        if self._opened:
            self._client.unmount_snapshot(lambda value, error: None)
