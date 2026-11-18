"""MountUsage on /proc: who has a file, a working folder or a watched folder inside the mount.

What scripts/verify_mount_activity.sh showed: a program with a file or its working folder in the
mount has it in /proc/<pid>/fd or /cwd, and Files showing a folder has it open and watched (inotify,
listed in /proc/<pid>/fdinfo). The gvfs daemons watch the top of every mount, always, so they never
count.
"""

import os
from collections.abc import Callable

IGNORED_PROGRAMS = ("gvfsd",)  # the name may carry a leading dot when a wrapper renamed the program


def kernel_device(st_dev: int) -> str:
    """How /proc/<pid>/fdinfo prints a device: major<<20|minor, in hex (not the st_dev encoding)."""
    return f"{(os.major(st_dev) << 20) | os.minor(st_dev):x}"


class ProcMountUsage:
    def __init__(
        self,
        proc: str = "/proc",
        stat: Callable[[str], os.stat_result] = os.stat,
        own_pid: int | None = None,
    ) -> None:
        self._proc = proc
        self._stat = stat
        self._own = str(os.getpid() if own_pid is None else own_pid)

    def users(self, mountpoint: str) -> list[str]:
        """Who uses the folder, as "name (pid): what" (empty when nobody does)."""
        device = kernel_device(self._stat(mountpoint).st_dev)
        found = []
        for entry in os.listdir(self._proc):
            if entry.isdigit() and entry != self._own:
                found += self._uses(entry, mountpoint, device)
        return sorted(found)

    def _uses(self, pid: str, mountpoint: str, device: str) -> list[str]:
        folder = os.path.join(self._proc, pid)
        try:
            with open(os.path.join(folder, "comm")) as comm:
                name = comm.read().strip()
            if name.lstrip(".").startswith(IGNORED_PROGRAMS):
                return []
            if self._holds(folder, mountpoint):
                return [f"{name} ({pid}): has a file or folder open"]
            if self._watches(folder, device):
                return [f"{name} ({pid}): watches a folder"]
        except OSError:
            pass  # gone since the listing, or not ours to look at
        return []

    @staticmethod
    def _holds(folder: str, mountpoint: str) -> bool:
        links = [os.path.join(folder, "cwd")]
        links += [os.path.join(folder, "fd", name) for name in os.listdir(os.path.join(folder, "fd"))]
        for link in links:
            try:
                target = os.readlink(link)
            except OSError:
                continue  # an fd closed meanwhile
            if target == mountpoint or target.startswith(mountpoint + os.sep):
                return True
        return False

    @staticmethod
    def _watches(folder: str, device: str) -> bool:
        info = os.path.join(folder, "fdinfo")
        for name in os.listdir(info):
            try:
                with open(os.path.join(info, name)) as text:
                    lines = text.read().splitlines()
            except OSError:
                continue
            if any(line.startswith("inotify") and f"sdev:{device} " in line for line in lines):
                return True
        return False
