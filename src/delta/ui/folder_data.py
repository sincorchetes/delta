"""What the folder browser lists, asked of the daemon: the folder, a search in it, or what changed."""

from collections.abc import Callable

from delta.i18n import _
from delta.ui.client import DeltaClient


class FolderData:
    """Each answer is for one place and one question: one that arrives after the user moved on, or
    asked something else, is dropped instead of replacing what is on screen."""

    def __init__(self, client: DeltaClient, on_ready: Callable[[], None], on_error: Callable[[str, str, str], None]) -> None:
        """`on_ready()`: something arrived. `on_error(kind, title, error)`: a question failed; `kind` is
        "listing", "search" or "changes"."""
        self._client, self._on_ready, self._on_error = client, on_ready, on_error
        self.snapshot = self.root = self.folder = ""
        self.listing: list[dict] = []  # the folder as the daemon described it
        self.hits: list[dict] | None = None  # the latest search; None when not searching or not arrived
        self.changes: list[dict] | None = None  # everything below that changed; None when not asked yet
        self.loading = False  # until the folder arrives `listing` is the previous folder's
        self.asking_changes = False
        self._ids = {"listing": 0, "search": 0, "changes": 0}

    def open(self, snapshot: str, root: str) -> None:
        """Start at `root` as it was in `snapshot`."""
        self.snapshot, self.root = snapshot, root
        self.enter(root)

    def enter(self, folder: str) -> None:
        """Move to another folder of the same snapshot: whatever was asked about the last is dropped."""
        self.folder = folder
        self.hits = self.changes = None
        self.asking_changes = False  # what was asked about the last folder is dropped when it arrives
        self._ids["search"] += 1
        self._ids["changes"] += 1
        self.loading = True
        self._ask("listing", lambda reply: self._client.list_folder(self.snapshot, folder, reply), _("Could not read this folder"))

    def search(self, query: str) -> None:
        self.hits = None
        self._ask("search", lambda reply: self._client.search_folder(self.snapshot, self.folder, query, reply), _("The search failed"))

    def clear_search(self) -> None:
        self.hits = None
        self._ids["search"] += 1

    def refresh_changes(self) -> None:
        """Compare with the disk again. What was known stays on screen until the new answer comes,
        so the marks do not blink out and back."""
        self.asking_changes = True
        self._ask("changes", lambda reply: self._client.list_changed(self.snapshot, self.folder, reply), _("Could not compare with the disk"))

    def ensure_changes(self) -> None:
        """Ask for the comparison unless it is known or already on its way."""
        if self.changes is None and not self.asking_changes:
            self.refresh_changes()

    def _ask(self, kind: str, call: Callable[[Callable], None], failure: str) -> None:
        self._ids[kind] += 1
        mine = self._ids[kind]

        def answer(rows, error) -> None:
            if mine != self._ids[kind]:
                return
            if kind == "listing":
                self.loading = False
            elif kind == "changes":
                self.asking_changes = False
            if error:
                self._on_error(kind, failure, error)
                return
            setattr(self, {"listing": "listing", "search": "hits", "changes": "changes"}[kind], rows)
            self._on_ready()
            if kind == "listing":
                self.ensure_changes()  # in the background: the marks on folders arrive when they arrive

        call(answer)
