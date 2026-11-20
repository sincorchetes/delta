#!/usr/bin/env python3
"""A real backup and a real restore with the package a user installed from the repository.

Not the source tree and not the test suite: the installed daemon (`/usr/libexec/delta-daemon`), with its own keyring, session
bus, HOME and settings (see scripts/smoke_session.py, whose session it reuses), asked over D-Bus to make a repository, back up
a few files, list them and restore one as a copy.

    python3 scripts/ci/package_smoke.py [PREFIX]   the package installed under PREFIX (default /usr)
    python3 scripts/ci/package_smoke.py --source   what `meson install` puts in a prefix of its own, from this source tree
"""

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import smoke_session as smoke  # noqa: E402
from gi.repository import Gio, GLib  # noqa: E402

FILES = {"notes.txt": "version 1", "folder with spaces/inner [1].txt": "inside", "línea-ñandú.txt": "unicode"}


def finished(session, job, timeout=120):
    done = session.wait_event("BackupFinished", 0, timeout, job)
    return bool(done and done[1][1]), (done[1][2] if done else "no answer")


def create_repository(session) -> bool:
    (job,) = session.call("CreateRepository", GLib.Variant("(ss)", (str(session.repo), "")))  # the passphrase goes to the keyring
    ok, message = finished(session, job, 60)
    return smoke.record("a repository, with its passphrase in the keyring", ok, message)


def backup(session) -> bool:
    (job,) = session.call("CreateBackup")
    ok, message = finished(session, job)
    return smoke.record("a backup of the home folder", ok and not message, message)


def restore(session, home: Path) -> bool:
    snapshots = session.call("ListSnapshots")[0]
    smoke.record("the backup is listed", len(snapshots) == 1, f"({len(snapshots)})")
    if len(snapshots) != 1:
        return False
    notes = str(home / "notes.txt")
    versions = session.call("ListVersions", GLib.Variant("(s)", (notes,)))[0]
    smoke.record("the file has a version in it", len(versions) >= 1, f"({len(versions)})")
    (home / "notes.txt").write_text("version 2")  # what the file is today
    (job,) = session.call("RestoreAsCopy", GLib.Variant("(ss)", (snapshots[0]["id"], notes)))
    ok, copy = finished(session, job)
    smoke.record("restore as a copy answers with the path it made", ok and Path(copy).is_file(), copy)
    return ok and Path(copy).read_text() == "version 1" and (home / "notes.txt").read_text() == "version 2"


def main() -> int:
    arguments = sys.argv[1:]
    from_source = "--source" in arguments
    prefix = Path(next((argument for argument in arguments if argument != "--source"), "/usr"))
    work = Path(tempfile.mkdtemp(prefix="delta-package-smoke-"))
    session = smoke.Session(work, 0, None if from_source else prefix)
    bus = Gio.TestDBus.new(Gio.TestDBusFlags.NONE)
    bus.up()
    keyring = daemon = None
    try:
        if not session.install():
            return 1
        session.environment(bus.get_bus_address())
        session.connect(bus.get_bus_address())
        for name, text in FILES.items():
            path = session.home / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        keyring = session.start_keyring()
        if keyring is None:
            return 1
        daemon = session.start_daemon()
        if not smoke.record("the daemon owns its name on the bus", session.name_owned(smoke.NAME)):
            session.show_log(daemon)
            return 1
        steps = (create_repository, backup)
        if all(step(session) for step in steps):
            smoke.record("the restored copy is the old version and the file is as it is today", restore(session, session.home))
    finally:
        smoke.stop(daemon)
        smoke.stop(keyring)
        bus.down()
        shutil.rmtree(work, ignore_errors=True)
    failed = [name for name, ok, _detail in smoke.results if not ok]
    print(f"\n{len(smoke.results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed or not smoke.results else 0


if __name__ == "__main__":
    raise SystemExit(main())
