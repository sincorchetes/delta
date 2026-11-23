"""Everything that PyGObject puts in `gi.repository` (Gtk, Gio, GLib, Adw, Secret...) is typed as Any: it has no stubs.

Without this, Pyright reports each name as an unknown import symbol, and what is left of its report is noise. The checking
is of Delta's own code; what it passes to GTK or gets back is not looked at.
"""

from typing import Any

def __getattr__(name: str) -> Any: ...
