"""Delta survives on a system where GTK cannot make its player.

Run it where the GStreamer plugins are missing (the Distributions workflow takes them away on Ubuntu), with a display:

    xvfb-run -a python3 scripts/ci/check_without_gstreamer.py

First it proves the premise, since otherwise nothing is proved: making the player in a process of its own ends that process.
Then it asks Delta's probe, which has to say that the player cannot be made, in this process, that goes on.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import gi

gi.require_version("Gio", "2.0")
from gi.repository import GLib

from delta.ui.media_probe import PROBE, MediaProbe

premise = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True)
if premise.returncode == 0:
    sys.exit("The player can be made here, so there is nothing to prove: the plugins were not taken away.")
print(f"Premise: making the player ends its process here (exit status {premise.returncode}).")
print(premise.stderr.strip()[-300:])

loop = GLib.MainLoop()
found: list[bool] = []
MediaProbe().check(lambda supported: (found.append(supported), loop.quit()))
GLib.timeout_add_seconds(30, loop.quit)
loop.run()

if found != [False]:
    sys.exit(f"The probe said {found} where it has to say [False].")
print("Delta's probe says that there is no player, and this process is still alive.")
