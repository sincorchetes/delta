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
import glob
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parent.parent
NAME, PATH = "io.github.sincorchetes.Delta.Service1", "/io/github/sincorchetes/Delta/Service1"
MARKER = "delta/backup-in-progress"
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}".rstrip(), flush=True)
    return ok


def pump(predicate, timeout: float) -> bool:
    context, deadline = GLib.MainContext.default(), time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        context.iteration(False)
        time.sleep(0.02)
    return predicate()


class Session:
    def __init__(self, work: Path, size_mb: int, package: Path | None = None) -> None:
        self.work, self.size_mb, self.package = work, size_mb, package
        self.prefix, self.xdg = package or work / "prefix", work / "xdg"
        self.home, self.repo = work / "home", work / "repo"
        self.events: list[tuple[str, tuple]] = []
        self.killed: set[str] = set()
        self.daemons = 0

    def install(self) -> bool:
        if self.package is not None:
            exe = self.package / "libexec" / "delta-daemon"
            return record("using the prebuilt package", exe.exists(), str(self.package))
        build = self.work / "build"
        for argv in (
            ["meson", "setup", str(build), f"--prefix={self.prefix}"],
            ["meson", "install", "-C", str(build), "--quiet"],
        ):
            done = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
            if done.returncode:
                return record("meson install", False, done.stderr[-400:])
        return record("meson install (isolated prefix)", True)

    def environment(self, bus_address: str) -> dict[str, str]:
        for sub in ("config", "data", "state", "run"):
            (self.xdg / sub).mkdir(parents=True, exist_ok=True)
        (self.xdg / "run").chmod(0o700)
        self.home.mkdir(exist_ok=True)
        site = glob.glob(str(self.prefix / "lib" / "python3*" / "site-packages"))
        env = {k: v for k, v in os.environ.items() if not k.startswith("BORG_")}
        env.update(
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.xdg / "config"),
            XDG_DATA_HOME=str(self.xdg / "data"),
            XDG_STATE_HOME=str(self.xdg / "state"),
            XDG_RUNTIME_DIR=str(self.xdg / "run"),
            GSETTINGS_BACKEND="keyfile",
            DBUS_SESSION_BUS_ADDRESS=bus_address,
        )
        if self.package is None:
            env["GSETTINGS_SCHEMA_DIR"] = str(self.prefix / "share" / "glib-2.0" / "schemas")
            env["PYTHONPATH"] = os.pathsep.join(site)
        else:
            # Hermetic: only what the package's own wrapper provides may be found.
            for leaked in ("PYTHONPATH", "GI_TYPELIB_PATH", "GSETTINGS_SCHEMA_DIR", "XDG_DATA_DIRS", "VIRTUAL_ENV"):
                env.pop(leaked, None)
        self.env = env
        return env

    def connect(self, bus_address: str) -> None:
        self.conn = Gio.DBusConnection.new_for_address_sync(
            bus_address,
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None,
            None,
        )
        for signal_name in ("Progress", "BackupFinished"):
            self.conn.signal_subscribe(
                None, NAME, signal_name, PATH, None, Gio.DBusSignalFlags.NONE,
                lambda c, s, o, i, member, params: self.events.append((member, params.unpack())),
            )

    def name_owned(self, name: str) -> bool:
        reply = self.conn.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "NameHasOwner", GLib.Variant("(s)", (name,)), None, Gio.DBusCallFlags.NONE, -1, None,
        )
        return reply.unpack()[0]

    def start_keyring(self) -> subprocess.Popen | None:
        if shutil.which("gnome-keyring-daemon") is None:
            record("gnome-keyring-daemon available", False, "install gnome-keyring")
            return None
        process = subprocess.Popen(
            ["gnome-keyring-daemon", "--foreground", "--components=secrets", "--unlock"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=self.env,
        )
        process.stdin.write(b"smoke\n")
        process.stdin.close()
        record("keyring ready", pump(lambda: self.name_owned("org.freedesktop.secrets"), 10))
        return process

    def start_daemon(self) -> subprocess.Popen:
        self.daemons += 1
        log = open(self.work / f"daemon-{self.daemons}.log", "w")
        exe = str(self.prefix / "libexec" / "delta-daemon")
        # A packaged daemon is self-contained (wrapper + shebang); a meson prefix is not.
        argv = [exe] if self.package else [sys.executable, exe]
        process = subprocess.Popen(
            argv, env=self.env, stdout=log, stderr=log, start_new_session=True,
        )
        pump(lambda: self.name_owned(NAME) or process.poll() is not None, 15)
        return process

    def show_log(self, daemon: subprocess.Popen, lines: int = 40) -> None:
        """Print what the daemon said before dying (the tree is deleted afterwards)."""
        state = "still running" if daemon.poll() is None else f"exited with {daemon.poll()}"
        log = self.work / f"daemon-{self.daemons}.log"
        tail = log.read_text().splitlines()[-lines:] if log.exists() else ["<no log>"]
        print(f"--- daemon {state}; last log lines ---")
        print("\n".join(tail))
        print("---")

    def call(self, method: str, params=None):
        return self.conn.call_sync(
            NAME, PATH, NAME, method, params, None, Gio.DBusCallFlags.NONE, 15000, None
        ).unpack()

    def wait_event(
        self, member: str, after: int, timeout: float, job: str | None = None,
        ignore_jobs: frozenset[str] = frozenset(),
    ):
        def found():
            return next(
                (
                    e for e in self.events[after:]
                    if e[0] == member and e[1][0] not in ignore_jobs and (job is None or e[1][0] == job)
                ),
                None,
            )

        pump(lambda: found() is not None, timeout)
        return found()

    def finished_jobs(self) -> frozenset[str]:
        """Jobs to ignore: already finished, or killed by this script (their signal may arrive late)."""
        done = {e[1][0] for e in self.events if e[0] == "BackupFinished"}
        return frozenset(done | self.killed)

    def marker(self) -> bool:
        return (self.xdg / "state" / MARKER).exists()

    def add_data(self, name: str) -> None:
        (self.home / name).write_bytes(os.urandom(self.size_mb * 1024 * 1024))


def stop(process: subprocess.Popen | None) -> None:
    if process and process.poll() is None:
        process.terminate()
        process.wait(timeout=10)


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
        "--package", type=Path,
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
