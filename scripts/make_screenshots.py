"""Render Delta's windows with made-up data into website/src/assets/screenshots/.

Run it inside `devenv shell`; it starts its own virtual display (xvfb-run), so nothing ever opens on your desktop:

    uv run python scripts/make_screenshots.py

Each window is drawn in English and Spanish, light and dark: `<name>-<lang>-<theme>.png`. Nothing from your
own files or backups is read: a stand-in client answers with the sample data below.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "website" / "src" / "assets" / "screenshots"
LANGUAGES = ("en", "es")
SAMPLE_KEY = "ABCDE-FGHJK-LMNPQ-RSTUV-WXYZ2-34567"  # made up: the format of a recovery key, nothing real
NOW = int(time.time())
SAMPLE_HOME = "/home/user"
VIRTUAL = "DELTA_SCREENSHOTS_ON_XVFB"  # set once the script runs under its own virtual display
SCALE = 2  # drawn at twice the size, so they stay sharp on high-density screens; the site shows them at their normal size


def parent_process() -> None:
    """Draw every language in its own process: gettext binds one language per process.

    Always on a virtual display: it starts one itself, so no window can ever open on the desktop. (A check of
    the environment cannot tell a virtual display from the real one: under `xvfb-run` the desktop's own
    WAYLAND_DISPLAY is still set.)
    """
    if os.environ.get(VIRTUAL) != "1":
        runner = shutil.which("xvfb-run")
        if runner is None:
            sys.exit("xvfb-run is needed (it is in the devenv shell): it gives the windows a display of their own.")
        # A big screen: without a window manager a window cannot be taller or wider than the screen it is on.
        screen = ["-s", "-screen 0 1600x1200x24"]
        os.execve(runner, [runner, "-a", *screen, sys.executable, __file__], {**os.environ, VIRTUAL: "1"})
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        for lang in LANGUAGES:
            catalog = Path(work) / lang / "LC_MESSAGES"
            catalog.mkdir(parents=True)
            if lang != "en":
                subprocess.run(["msgfmt", "-o", str(catalog / "delta.mo"), str(ROOT / "po" / f"{lang}.po")], check=True)
            env = {k: v for k, v in os.environ.items() if k != "WAYLAND_DISPLAY"}
            env |= {"DELTA_LOCALEDIR": work, "LANGUAGE": lang, "LC_ALL": "C.UTF-8", "GDK_BACKEND": "x11"}
            subprocess.run([sys.executable, __file__, "--lang", lang], check=True, env=env)


# --- everything below runs once per language -------------------------------------------------------


class SampleClient:
    """Answers each daemon call at once with canned data; remembers subscriptions."""

    def __init__(self, files: Path) -> None:
        self.files = files
        self.handlers: dict = {}
        self.is_dir = False  # whether the versions asked for belong to a folder

    def __getattr__(self, method: str):
        if method.startswith("on_"):
            return lambda handler: self.handlers.setdefault(method, handler) and 1
        return lambda *arguments: self._answer(method, arguments)

    def unsubscribe(self, subscription) -> None:
        pass

    def _answer(self, method: str, arguments: tuple) -> None:
        if not arguments or not callable(arguments[-1]):
            return  # a call nobody waits for an answer to (clear_previews when a window closes)
        reply = arguments[-1]
        answers = {
            "read_state": ({"Status": "idle", "LastBackup": NOW - 300, "NextBackup": NOW + 1500, "LastError": "",
                            "CanMount": True}, None),
            "list_snapshots": (
                [{"id": f"{i:08x}", "name": f"user-{i}", "time": NOW - hours * 3600}
                 for i, hours in enumerate((1, 5, 26, 50, 24 * 8, 24 * 30), 1)], None),
            "list_versions": (
                [{"name": f"v{i}", "time": NOW - hours * 3600, "mtime": NOW - hours * 3600 - 60,
                  "size": 14_000 + i * 900, "is_dir": self.is_dir} for i, hours in enumerate((2, 30, 100, 400), 1)], None),
            "list_folder": (self._listing(), None),
            "preview_version": ("preview", None),
        }
        if method in answers:
            reply(*answers[method])
        if method == "preview_version" and "on_backup_finished" in self.handlers:
            self.handlers["on_backup_finished"]("preview", True, str(self.files / "Quarterly report.txt"))

    @staticmethod
    def _listing() -> list[dict]:
        names = (("Budget 2026.ods", False, 48_200), ("Quarterly report.odt", False, 31_400),
                 ("Meeting notes.txt", False, 2_100), ("Photos", True, 0), ("Receipts", True, 0))
        return [{"name": n, "is_dir": d, "size": s, "mtime": NOW - 86400 * (i + 1)} for i, (n, d, s) in enumerate(names)]


def settings_in_memory():
    """Real GSettings on a throwaway in-memory backend, with the project's own schema."""
    from gi.repository import Gio

    schemas = Path(tempfile.mkdtemp())
    subprocess.run(["glib-compile-schemas", "--targetdir", str(schemas), str(ROOT / "data")], check=True)
    source = Gio.SettingsSchemaSource.new_from_directory(str(schemas), None, False)
    settings = Gio.Settings.new_full(source.lookup("io.github.sincorchetes.Delta", False), Gio.memory_settings_backend_new(), None)
    settings.set_string("repository-location", "/run/media/user/Backups/delta-backups")
    return settings


def pump(seconds: float) -> None:
    from gi.repository import GLib

    context, end = GLib.MainContext.default(), time.monotonic() + seconds
    while time.monotonic() < end:
        context.iteration(False)
        time.sleep(0.01)


def shoot(window, name: str, lang: str) -> None:
    """Save `window` as it is now, once per colour scheme."""
    from gi.repository import Adw, Graphene, Gsk, Gtk

    for scheme, theme in ((Adw.ColorScheme.FORCE_LIGHT, "light"), (Adw.ColorScheme.FORCE_DARK, "dark")):
        Adw.StyleManager.get_default().set_color_scheme(scheme)
        pump(0.8)
        width, height = window.get_width(), window.get_height()
        snapshot = Gtk.Snapshot()
        Gtk.WidgetPaintable.new(window).snapshot(snapshot, width, height)
        # The scene is vector: scaling it before it is rendered gives sharp text, not an enlarged bitmap.
        node = Gsk.TransformNode.new(snapshot.to_node(), Gsk.Transform.new().scale(SCALE, SCALE))
        area = Graphene.Rect().init(0, 0, width * SCALE, height * SCALE)
        texture = window.get_native().get_renderer().render_texture(node, area)
        texture.save_to_png(str(OUT / f"{name}-{lang}-{theme}.png"))


def show(window, width: int, height: int) -> None:
    window.set_default_size(width, height)
    window.present()
    pump(1.2)


def child_process(lang: str) -> None:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gsk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw

    from delta import i18n

    i18n.setup()
    files = Path(tempfile.mkdtemp())
    (files / "Quarterly report.txt").write_text(
        "Quarterly report\n\nRevenue grew in the third quarter.\nCosts stayed flat.\n\nNext steps\n- Review the budget\n"
    )
    Adw.init()
    app = Adw.Application(application_id="io.github.sincorchetes.DeltaScreenshots")
    app.register(None)
    client, settings = SampleClient(files), settings_in_memory()

    from delta.ui import wizard_window
    from delta.ui.history_window import HistoryWindow
    from delta.ui.preferences_dialog import PreferencesDialog
    from delta.ui.versions_window import VersionsWindow
    from delta.ui.window import StatusWindow
    from delta.ui.wizard import Step, WizardModel

    status = StatusWindow(app, client, settings)
    show(status, 640, 720)
    shoot(status, "status", lang)

    PreferencesDialog(settings, SAMPLE_HOME, status).present(status)
    pump(1.0)
    shoot(status, "preferences", lang)
    status.close()

    history = HistoryWindow(None, client)
    show(history, 620, 460)
    shoot(history, "history", lang)
    history.close()

    wizard_window.WizardModel = lambda **fields: WizardModel(**fields, recovery_key=SAMPLE_KEY)
    wizard = wizard_window.SetupWizard(None, client, settings, lambda: None)
    wizard._model.destination = str(files)
    show(wizard, 560, 640)
    shoot(wizard, "wizard-destination", lang)
    wizard._model.step = Step.RECOVERY
    wizard._show()
    pump(0.5)
    shoot(wizard, "wizard-recovery", lang)
    wizard.close()

    document = files / "Quarterly report.odt"
    document.write_text("x")
    versions = VersionsWindow(app, client, str(document))
    show(versions, 900, 640)
    pump(1.0)
    shoot(versions, "versions", lang)
    versions.close()

    folder = files / "Documents"
    folder.mkdir()
    client.is_dir = True
    browser = VersionsWindow(app, client, str(folder))
    show(browser, 900, 640)
    pump(1.0)
    shoot(browser, "folder", lang)
    browser.close()
    shutil.rmtree(files, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", choices=LANGUAGES)
    options = parser.parse_args()
    child_process(options.lang) if options.lang else parent_process()
