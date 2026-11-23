"""Remembers what `borg list` said about a path of a snapshot.

A snapshot never changes, so what borg listed stays right until the snapshot is pruned; there is
nothing to invalidate. And since listing a folder lists everything below it, a folder inside one
already listed is cut out of that listing instead of asking borg again. Held in memory only, and
bounded: the least recently used answers go first.
"""

import json
import threading
from collections import OrderedDict

MAX_BYTES = 96_000_000  # about half a million listed entries


def _cut(listing: str, path: str) -> str:
    """The lines of `listing` that are `path` or below it (what borg would say about `path`)."""
    prefix = path.lstrip("/")
    below = prefix + "/"
    kept = []
    for line in listing.splitlines():
        try:
            name = json.loads(line)["path"]
        except (ValueError, KeyError, TypeError):
            continue  # not an entry: borg lists nothing else, so there is nothing to keep
        if name == prefix or name.startswith(below):
            kept.append(line)
    return "\n".join(kept)


class ListingCache:
    def __init__(self, max_bytes: int = MAX_BYTES) -> None:
        self._max = max_bytes
        self._items: OrderedDict[tuple[str, str, str], str] = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def get(self, repo: str, snapshot: str, path: str) -> str | None:
        """What borg listed for `path`, from memory; None when borg has to be asked."""
        with self._lock:
            found = self._items.get((repo, snapshot, path))
            if found is not None:
                self._items.move_to_end((repo, snapshot, path))
                return found
            ancestor = self._closest_ancestor(repo, snapshot, path)
        if ancestor is None:
            return None
        derived = _cut(ancestor, path)
        self.put(repo, snapshot, path, derived)
        return derived

    def put(self, repo: str, snapshot: str, path: str, listing: str) -> None:
        key = (repo, snapshot, path)
        with self._lock:
            if key in self._items:
                self._bytes -= len(self._items.pop(key))
            self._items[key] = listing
            self._bytes += len(listing)
            while self._bytes > self._max and len(self._items) > 1:
                oldest = next(iter(self._items))
                self._bytes -= len(self._items.pop(oldest))

    def _closest_ancestor(self, repo: str, snapshot: str, path: str) -> str | None:
        around = [
            key for key in self._items if key[0] == repo and key[1] == snapshot and path.startswith(key[2].rstrip("/") + "/")
        ]
        if not around:
            return None
        best = max(around, key=lambda key: len(key[2]))
        self._items.move_to_end(best)
        return self._items[best]
