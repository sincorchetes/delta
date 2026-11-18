"""The Home Manager module links, into XDG_DATA_HOME, what the desktop looks for there."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = (ROOT / "nix" / "home-manager.nix").read_text(encoding="utf-8")


def test_the_manual_is_linked_where_yelp_looks_for_it():
    block = re.search(r'"help" = \{\s*source = "\$\{share\}/help";\s*recursive = true;\s*\};', MODULE)

    assert block is not None


def test_what_a_session_needs_to_find_without_the_nix_profile_in_its_data_dirs_is_linked():
    for target in ("systemd/user", "dbus-1/services", "locale", "glib-2.0/schemas", "help"):
        assert f'"{target}" = {{' in MODULE, target
    for entry in ("Delta", "Delta.Daemon", "Delta.Versions"):
        assert f'"applications/io.github.sincorchetes.{entry}.desktop"' in MODULE, entry
