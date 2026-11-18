"""What the daemon runs inside of: a Flatpak sandbox or the plain system."""

import os

FLATPAK_MARKER = "/.flatpak-info"  # Flatpak puts this file in every sandbox


def in_flatpak(marker: str = FLATPAK_MARKER) -> bool:
    return os.path.exists(marker)
