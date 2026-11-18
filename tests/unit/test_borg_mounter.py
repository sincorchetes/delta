"""BorgMounter against a script that stands in for `borg mount`.

The folder "being mounted" is a marker file next to it (`<mountpoint>.up`), so no FUSE is needed.
"""

import os
import sys

import pytest

from delta.domain.errors import EngineError, RepositoryLocked
from delta.domain.repository import Repository
from delta.infrastructure import borg_commands, borg_mounter
from delta.infrastructure.borg_mounter import BorgMounter
from delta.infrastructure.borg_runner import BorgRunner

REPO = Repository("/r")

STAND_IN = """#!{python}
import os, pathlib, signal, sys, time

mode = os.environ["STAND_IN"]
marker = pathlib.Path(sys.argv[-1] + ".up")

if mode == "lock":
    sys.stderr.write("Failed to create/acquire the lock /r/lock.exclusive (timeout).\\n")
    sys.exit(2)
if mode == "lazy-only":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
elif mode == "deaf":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if mode != "never":
    marker.write_text("up")
while True:
    time.sleep(0.05)
"""


@pytest.fixture
def world(tmp_path, monkeypatch):
    script = tmp_path / "borg-mount"
    script.write_text(STAND_IN.format(python=sys.executable))
    script.chmod(0o755)
    folder = str(tmp_path / "mnt")
    marker = folder + ".up"
    monkeypatch.setattr(
        borg_commands, "lazy_unmount", lambda mountpoint: ["rm", "-f", mountpoint + ".up"]
    )

    def build(mode, **limits):
        runner = BorgRunner(env={"STAND_IN": mode})
        return BorgMounter(
            runner, binary=str(script), is_mounted=lambda path: os.path.exists(path + ".up"), **limits
        )

    return build, folder, marker


def test_mounting_waits_for_the_folder_and_unmounting_removes_it(world):
    build, folder, marker = world
    mounter = build("lazy-only")

    mounter.mount(REPO, "monday", folder)
    assert os.path.exists(marker)

    mounter.unmount(folder)
    assert not os.path.exists(marker)


def test_a_second_mount_is_refused_while_one_is_open(world):
    build, folder, _marker = world
    mounter = build("lazy-only")
    mounter.mount(REPO, "monday", folder)
    try:
        with pytest.raises(EngineError, match="already open"):
            mounter.mount(REPO, "tuesday", folder)
    finally:
        mounter.unmount(folder)


def test_borg_refusing_the_mount_says_why(world):
    build, folder, _marker = world
    with pytest.raises(RepositoryLocked, match="lock"):
        build("lock").mount(REPO, "monday", folder)


def test_a_folder_that_never_appears_gives_up_and_leaves_nothing_running(world):
    build, folder, _marker = world
    mounter = build("never", ready_timeout=0.3, stop_timeout=5)

    with pytest.raises(EngineError, match="did not open in time"):
        mounter.mount(REPO, "monday", folder)

    assert mounter._process is None


def test_a_mount_process_that_ignores_sigterm_is_forced_out(world):
    build, folder, marker = world
    mounter = build("deaf", stop_timeout=0.3)
    mounter.mount(REPO, "monday", folder)

    mounter.unmount(folder)

    assert not os.path.exists(marker)
    assert mounter._ended.is_set()


def test_unmounting_when_nothing_was_mounted_is_harmless(world):
    build, folder, _marker = world
    build("lazy-only").unmount(folder)


def test_a_folder_that_stays_mounted_is_reported(world, monkeypatch):
    build, folder, _marker = world
    monkeypatch.setattr(borg_commands, "lazy_unmount", lambda mountpoint: ["true"])
    mounter = build("lazy-only")
    mounter.mount(REPO, "monday", folder)
    try:
        with pytest.raises(EngineError, match="could not be closed"):
            mounter.unmount(folder)
    finally:
        os.unlink(folder + ".up")


def test_a_failed_cleanup_does_not_hide_why_the_mount_failed(world, monkeypatch):
    build, folder, _marker = world
    mounter = build("never", ready_timeout=0.2)

    def stuck(mountpoint):
        raise EngineError("the snapshot could not be closed")

    monkeypatch.setattr(mounter, "unmount", stuck)

    with pytest.raises(EngineError, match="did not open in time"):
        mounter.mount(REPO, "monday", folder)


def test_a_missing_borg_is_an_engine_error(tmp_path):
    mounter = BorgMounter(BorgRunner(), binary=str(tmp_path / "nope"))
    with pytest.raises(EngineError, match="cannot run"):
        mounter.mount(REPO, "monday", str(tmp_path))


def test_a_missing_fusermount_is_left_to_the_final_check(world, monkeypatch):
    build, folder, marker = world
    monkeypatch.setattr(borg_commands, "lazy_unmount", lambda mountpoint: ["/no/such/fusermount"])
    mounter = build("lazy-only")
    mounter.mount(REPO, "monday", folder)
    try:
        with pytest.raises(EngineError, match="could not be closed"):
            mounter.unmount(folder)
    finally:
        os.unlink(marker)


def test_the_defaults_are_a_few_seconds():
    assert borg_mounter.READY_TIMEOUT > borg_mounter.POLL
    assert borg_mounter.STOP_TIMEOUT >= 1
