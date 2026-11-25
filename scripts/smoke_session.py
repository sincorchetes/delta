#!/usr/bin/env python3
"""End-to-end smoke of the *installed* daemon in a fully isolated session.

Own prefix, HOME, XDG dirs, session bus, keyring and GSettings (keyfile
backend): nothing of the user's real session is touched. `systemctl --user`
cannot reach the real manager from here, so the timer itself is not started;
only the drop-in written by the scheduler is checked.

Run inside `devenv shell`:  uv run python scripts/smoke_session.py [--keep]
Against the Nix build:      uv run python scripts/smoke_session.py --package result
The GTK app, isolated:      uv run python scripts/smoke_session.py --package result --ui
"""

import argparse
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from smoke_support import NAME, Session, pump, record, results, stop


def phase_create_repository(s: Session) -> bool:
    mark = len(s.events)
    (job,) = s.call("CreateRepository", GLib.Variant("(ss)", (str(s.repo), "")))
    done = s.wait_event("BackupFinished", mark, 60, job)
    ok = bool(done and done[1][1])
    dropin = s.xdg / "config" / "systemd" / "user" / "delta.timer.d" / "schedule.conf"
    pump(dropin.exists, 10)
    record("CreateRepository (passphrase generated into the keyring)", ok, "" if ok else str(done))
    record("scheduler wrote the timer drop-in", dropin.exists(), dropin.read_text().strip() if dropin.exists() else "")
    return ok


def phase_sigterm(s: Session, daemon: subprocess.Popen) -> bool:
    mark = len(s.events)
    (job,) = s.call("CreateBackup")
    s.killed.add(job)
    if not s.wait_event("Progress", mark, 90, job):
        return record("backup started (progress seen)", False)
    started = time.monotonic()
    daemon.send_signal(signal.SIGTERM)
    try:
        daemon.wait(timeout=30)
    except subprocess.TimeoutExpired:
        return record("SIGTERM stops the daemon quickly", False, "still running after 30 s")
    record("SIGTERM stops the daemon quickly", True, f"{time.monotonic() - started:.1f} s")
    return record("journal mark survives the interruption", s.marker())


def phase_resume(s: Session, label: str) -> tuple[bool, subprocess.Popen]:
    known = s.finished_jobs()
    daemon = s.start_daemon()
    done = s.wait_event("BackupFinished", 0, 300, ignore_jobs=known)
    ok = bool(done and done[1][1])
    detail = "" if ok else str(done)
    record(f"{label}: restart resumes the backup", ok, detail)
    record(f"{label}: journal mark cleared", pump(lambda: not s.marker(), 10))
    return ok, daemon


def phase_sigkill(s: Session, daemon: subprocess.Popen) -> None:
    s.add_data("more.bin")
    mark = len(s.events)
    (job,) = s.call("CreateBackup")
    s.killed.add(job)
    if not s.wait_event("Progress", mark, 90, job):
        record("second backup started (progress seen)", False)
        return
    os.killpg(os.getpgid(daemon.pid), signal.SIGKILL)  # daemon and its borg, like a power cut
    daemon.wait(timeout=10)
    record("SIGKILL leaves the journal mark", s.marker())
    known = s.finished_jobs()
    resumed = s.start_daemon()
    done = s.wait_event("BackupFinished", 0, 300, ignore_jobs=known)
    ok = bool(done and done[1][1])
    print(f"[INFO] after SIGKILL the resumed backup {'succeeded' if ok else 'FAILED: ' + str(done)}")
    record("after SIGKILL the backup resumes by itself", ok, "" if ok else "see INFO above (stale lock?)")
    stop(resumed)


def run(work: Path, size_mb: int, package: Path | None = None) -> None:
    s = Session(work, size_mb, package)
    if not s.install():
        return
    bus = Gio.TestDBus.new(Gio.TestDBusFlags.NONE)
    bus.up()
    keyring = daemon = None
    try:
        s.environment(bus.get_bus_address())
        s.connect(bus.get_bus_address())
        keyring = s.start_keyring()
        if keyring is None:
            return
        s.add_data("big.bin")
        daemon = s.start_daemon()
        if not record("daemon owns io.github.sincorchetes.Delta.Service1", s.name_owned(NAME)):
            s.show_log(daemon)
            return
        if not phase_create_repository(s):
            return
        if not phase_sigterm(s, daemon):
            return
        ok, daemon = phase_resume(s, "after SIGTERM")
        snapshots = s.call("ListSnapshots")[0]
        record("snapshot exists after resume", len(snapshots) == 1, f"({len(snapshots)})")
        if ok:
            phase_sigkill(s, daemon)
        else:
            s.show_log(daemon)
    finally:
        stop(daemon)
        stop(keyring)
        bus.down()


def run_ui(work: Path, package: Path) -> int:
    """Open the GTK app against an isolated daemon, keyring and GSettings; nothing real is touched."""
    s = Session(work, 0, package)
    if not s.install():
        return 1
    bus = Gio.TestDBus.new(Gio.TestDBusFlags.NONE)
    bus.up()
    keyring = daemon = None
    try:
        env = s.environment(bus.get_bus_address())
        s.connect(bus.get_bus_address())
        keyring = s.start_keyring()
        daemon = s.start_daemon()
        if keyring is None or not record("daemon owns io.github.sincorchetes.Delta.Service1", s.name_owned(NAME)):
            s.show_log(daemon)
            return 1
        # The isolated XDG_RUNTIME_DIR hides the real Wayland socket: point to it explicitly.
        wayland = os.environ.get("WAYLAND_DISPLAY", "")
        if wayland and not os.path.isabs(wayland):
            env["WAYLAND_DISPLAY"] = os.path.join(os.environ.get("XDG_RUNTIME_DIR", ""), wayland)
        print("\nDelta is open in an ISOLATED session. Use the wizard, then close the window.\n", flush=True)
        subprocess.run([str(package / "bin" / "delta-ui")], env=env)
        report_ui_result(s)
        return 0
    finally:
        stop(daemon)
        stop(keyring)
        bus.down()


def report_ui_result(s: Session) -> None:
    keyfile = s.xdg / "config" / "glib-2.0" / "settings" / "keyfile"
    print("\n--- settings written in the isolated session ---")
    print(keyfile.read_text().strip() if keyfile.exists() else "(none: the wizard did not finish)")
    print("--- end ---")
    log = s.work / f"daemon-{s.daemons}.log"
    if log.exists():
        print("daemon log (tail):")
        print("\n".join(log.read_text().splitlines()[-12:]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ui", action="store_true", help="open the GTK app in an isolated session (needs --package)")
    parser.add_argument("--keep", action="store_true", help="keep the temporary tree for inspection")
    parser.add_argument("--size-mb", type=int, default=256, help="random data per backup (default 256)")
    parser.add_argument(
        "--package",
        type=Path,
        help="test an already built package (e.g. the Nix `result`) instead of a meson install",
    )
    args = parser.parse_args()
    package = args.package.resolve() if args.package else None
    work = Path(tempfile.mkdtemp(prefix="delta-smoke-"))
    print(f"working in {work}")
    try:
        if args.ui:
            if package is None:
                parser.error("--ui needs --package (e.g. --package result)")
            return run_ui(work, package)
        run(work, args.size_mb, package)
    finally:
        if args.keep:
            print(f"kept {work}  (daemon logs: daemon-*.log)")
        else:
            shutil.rmtree(work, ignore_errors=True)
    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed or not results else 0


if __name__ == "__main__":
    raise SystemExit(main())
