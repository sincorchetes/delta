"""Restore several paths of one backup, one after another: the daemon runs one job at a time."""

import os
from collections.abc import Callable

from delta.i18n import _, ngettext
from delta.ui.job_tracker import JobTracker
from delta.ui.status import summarise

Item = tuple[str, bool]  # (path, in_place): put it back under its own name, or beside what is there
Done = Callable[[list[str], list[str], list[str]], None]  # (where each went, why each failed, paths done)


class RestoreBatch:
    """Keeps going when one fails, so a single bad item does not stop the rest."""

    def __init__(self, client, tracker: JobTracker, snapshot: str, items: list[Item], on_done: Done) -> None:
        self._client, self._tracker = client, tracker
        self._snapshot, self._on_done = snapshot, on_done
        self._pending = list(items)
        self._current: str | None = None
        self._restored: list[str] = []  # where each one ended up
        self._failures: list[str] = []  # why each one did not
        self._done: list[str] = []  # the paths that were restored, as they were asked for

    def start(self) -> None:
        self._next()

    def _next(self) -> None:
        if not self._pending:
            self._on_done(self._restored, self._failures, self._done)
            return
        path, in_place = self._pending.pop(0)
        self._current = path
        self._tracker.begin(self._finished)
        start = self._client.restore_replace if in_place else self._client.restore_as_copy
        start(self._snapshot, path, self._tracker.on_started)

    def _finished(self, ok: bool, message: str) -> None:
        if ok:
            self._restored.append(message)
            self._done.append(self._current or "")
        else:
            self._failures.append(message)
        self._next()  # begins the next job before anything else can look at the tracker


def deleted_confirm_text(count: int, size: str) -> str:
    """What the dialog says before putting back everything that was deleted."""
    return ngettext(
        "{n} item ({size}) that was in this folder in this version and is gone now will be put back where it was. Nothing that exists now is touched.",
        "{n} items ({size}) that were in this folder in this version and are gone now will be put back where they were. Nothing that exists now is touched.",
        count,
    ).format(n=count, size=size)


def deleted_result_text(ok: bool, message: str) -> str:
    """The toast after it ran. `message` is how many items came back, as a decimal number."""
    if not ok:
        return summarise(message) or _("It could not be restored.")
    if message.isdigit() and int(message) > 0:
        return ngettext("Restored {n} item", "Restored {n} items", int(message)).format(n=int(message))
    return _("Nothing needed restoring.")


def summary(restored: list[str], failures: list[str], in_place: bool) -> str:
    """One sentence for a toast. `restored` holds paths (the first is named when there is one)."""
    if not failures:
        if len(restored) == 1:
            name = os.path.basename(restored[0])
            return (_("Restored {name}") if in_place else _("Restored as {name}")).format(name=name)
        return _("Restored {n} items").format(n=len(restored))
    reason = summarise(failures[0]) or _("It could not be restored.")
    if not restored:
        return reason if len(failures) == 1 else _("None could be restored: {reason}").format(reason=reason)
    return _("{done} restored, {failed} not: {reason}").format(done=len(restored), failed=len(failures), reason=reason)
