"""«Restore deleted…»: ask what is gone from the folder, confirm with the count, then put it all back.

Also the confirmation for replacing the current version of one item or several.
"""

from collections.abc import Callable

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw

from delta.i18n import _
from delta.ui.client import DeltaClient
from delta.ui.job_tracker import JobTracker
from delta.ui.restore_batch import deleted_confirm_text, deleted_result_text
from delta.ui.status import summarise
from delta.ui.versions import format_size


def confirm_replace(window, count: int, on_yes: Callable[[], None]) -> None:
    """Replacing is reversible (the current one is kept aside), but say so before doing it."""
    if count > 1:
        title = _("Replace {n} current versions?").format(n=count)
        body = _("The versions you chose take their place. The current ones are kept next to them, renamed with today's date and time.")
    else:
        title = _("Replace the current version?")
        body = _("The version you chose takes its place. The current one is kept next to it, renamed with today's date and time.")
    dialog = Adw.AlertDialog.new(title, body)
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("replace", _("Replace"))
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")
    dialog.choose(window, None, lambda dlg, result: on_yes() if dlg.choose_finish(result) == "replace" else None)


class RestoreDeleted:
    """One job in the daemon, however many items: it extracts all of them in one go."""

    def __init__(
        self,
        client: DeltaClient,
        tracker: JobTracker,
        window,
        toast: Callable[[str], None],
        on_change: Callable[[], None],
        on_done: Callable[[], None],
    ) -> None:
        self._client, self._tracker, self._window = client, tracker, window
        self._toast, self._on_change, self._on_done = toast, on_change, on_done

    def start(self, snapshot: str, folder: str) -> None:
        if self._tracker.busy:
            return
        self._client.list_deleted(
            snapshot, folder, lambda rows, error: self._confirm(snapshot, folder, rows, error)
        )

    def _confirm(self, snapshot: str, folder: str, rows, error) -> None:
        if error:
            self._toast(summarise(error))
            return
        if not rows:
            self._toast(_("Nothing was deleted from this folder since this version."))
            return
        size = format_size(sum(row["size"] for row in rows))
        dialog = Adw.AlertDialog.new(_("Restore everything deleted?"), deleted_confirm_text(len(rows), size))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("restore", _("Restore"))
        dialog.set_response_appearance("restore", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.choose(self._window, None, lambda dlg, result: self._answered(dlg, result, snapshot, folder))

    def _answered(self, dialog, result, snapshot: str, folder: str) -> None:
        if dialog.choose_finish(result) != "restore" or self._tracker.busy:
            return
        self._tracker.begin(self._finished)
        self._client.restore_deleted(snapshot, folder, self._tracker.on_started)
        self._on_change()

    def _finished(self, ok: bool, message: str) -> None:
        self._on_change()
        self._on_done()
        self._toast(deleted_result_text(ok, message))
