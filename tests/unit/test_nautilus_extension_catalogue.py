"""The extension's menu text: where its translations are looked for, and which Nautilus API it loads."""

import gettext
import importlib.util
import sys
import gi
import pytest
from nautilus_extension_support import EXTENSION, _compile
from nautilus_extension_support import extension  # noqa: F401  (fixtures)


def test_the_menu_text_is_translated_from_a_data_directory(extension, tmp_path):
    catalogue = tmp_path / "locale" / "es" / "LC_MESSAGES"
    catalogue.mkdir(parents=True)
    mo = _compile(catalogue, {"Restore Previous Version…": "Restaurar versión anterior…"})
    assert mo.exists()

    found = extension.translations([str(tmp_path)], languages=["es"])

    assert found.gettext("Restore Previous Version…") == "Restaurar versión anterior…"


def test_a_flatpak_install_is_looked_at_for_the_catalogue_after_the_system_ones(extension, tmp_path):
    dirs = extension.flatpak_share_dirs(str(tmp_path))

    assert dirs == [
        f"{tmp_path}/flatpak/app/io.github.sincorchetes.Delta/current/active/files/share",
        "/var/lib/flatpak/app/io.github.sincorchetes.Delta/current/active/files/share",
    ]


def test_the_menu_text_is_translated_from_a_flatpak_install_that_nautilus_can_read(extension, tmp_path):
    share = tmp_path / "flatpak" / "app" / "io.github.sincorchetes.Delta" / "current" / "active" / "files" / "share"
    catalogue = share / "locale" / "es" / "LC_MESSAGES"
    catalogue.mkdir(parents=True)
    _compile(catalogue, {"Restore Previous Version…": "Restaurar versión anterior…"})

    found = extension.translations(extension.flatpak_share_dirs(str(tmp_path)), languages=["es"])

    assert found.gettext("Restore Previous Version…") == "Restaurar versión anterior…"


def test_by_default_the_flatpak_folders_are_searched_too(extension, monkeypatch):
    asked = []

    def nothing_here(domain, localedir, languages=None):
        asked.append(localedir)
        raise OSError

    monkeypatch.setattr(extension.gettext, "translation", nothing_here)

    extension.translations(languages=["es"])

    assert any("/flatpak/app/io.github.sincorchetes.Delta/" in path for path in asked)


def test_without_any_catalogue_the_text_stays_in_english(extension, tmp_path):
    found = extension.translations([str(tmp_path)], languages=["es"])
    assert isinstance(found, gettext.NullTranslations)
    assert found.gettext("Restore Previous Version…") == "Restore Previous Version…"


def test_the_extension_never_imports_the_delta_package():
    """Nautilus runs it with a different interpreter, where `delta` is not importable."""
    source = EXTENSION.read_text(encoding="utf-8")
    assert "import delta" not in source and "from delta" not in source


def test_without_any_gtk4_nautilus_api_loading_fails_clearly(monkeypatch):
    def refuse(name, version):
        if name == "Nautilus":
            raise ValueError("Namespace Nautilus not available")

    monkeypatch.setattr(gi, "require_version", refuse)
    spec = importlib.util.spec_from_file_location("delta_extension_missing_api", EXTENSION)
    module = importlib.util.module_from_spec(spec)
    with pytest.raises(ImportError, match="Nautilus-4"):
        spec.loader.exec_module(module)


def test_the_newest_api_version_is_tried_first(monkeypatch, extension):
    asked = []
    nautilus = sys.modules["gi.repository.Nautilus"]
    monkeypatch.setattr(gi, "require_version", lambda name, version: asked.append((name, version)))
    spec = importlib.util.spec_from_file_location("delta_extension_order", EXTENSION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert asked[0] == ("Nautilus", "4.1") and nautilus is not None
