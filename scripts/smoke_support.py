"""What the smoke of the installed daemon shares: an isolated session (own HOME, bus, keyring and settings), and its results."""

import glob
import os
import shutil
import subprocess
import sys
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
        # where Meson put the Python package: site-packages, or dist-packages (Debian), under lib or lib64
        site = glob.glob(str(self.prefix / "lib*" / "python3*" / "*-packages"))
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
                None,
                NAME,
                signal_name,
                PATH,
                None,
                Gio.DBusSignalFlags.NONE,
                lambda c, s, o, i, member, params: self.events.append((member, params.unpack())),
            )

    def name_owned(self, name: str) -> bool:
        reply = self.conn.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "NameHasOwner",
            GLib.Variant("(s)", (name,)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        return reply.unpack()[0]

    def start_keyring(self) -> subprocess.Popen | None:
        if shutil.which("gnome-keyring-daemon") is None:
            record("gnome-keyring-daemon available", False, "install gnome-keyring")
            return None
        process = subprocess.Popen(
            ["gnome-keyring-daemon", "--foreground", "--components=secrets", "--unlock"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=self.env,
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
            argv,
            env=self.env,
            stdout=log,
            stderr=log,
            start_new_session=True,
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
        return self.conn.call_sync(NAME, PATH, NAME, method, params, None, Gio.DBusCallFlags.NONE, 15000, None).unpack()

    def wait_event(
        self,
        member: str,
        after: int,
        timeout: float,
        job: str | None = None,
        ignore_jobs: frozenset[str] = frozenset(),
    ):
        def found():
            return next(
                (
                    e
                    for e in self.events[after:]
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
