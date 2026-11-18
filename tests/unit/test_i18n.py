import shutil
import subprocess
from pathlib import Path

import pytest

from delta import i18n

SPANISH_PO = Path(__file__).resolve().parents[2] / "po" / "es.po"


def test_untranslated_message_is_returned_unchanged():
    assert i18n._("Hello") == "Hello"


def test_setup_survives_a_locale_that_is_not_generated(monkeypatch):
    def missing(*args):
        raise i18n.locale.Error("unsupported locale setting")

    monkeypatch.setattr(i18n.locale, "setlocale", missing)

    i18n.setup()

    assert i18n._("Hello") == "Hello"


@pytest.mark.skipif(shutil.which("msgfmt") is None, reason="msgfmt not installed")
def test_spanish_catalog_translates_daemon_messages(tmp_path, monkeypatch):
    messages = tmp_path / "es" / "LC_MESSAGES"
    messages.mkdir(parents=True)
    subprocess.run(["msgfmt", "-o", str(messages / "delta.mo"), str(SPANISH_PO)], check=True)
    monkeypatch.setenv("DELTA_LOCALEDIR", str(tmp_path))
    monkeypatch.setenv("LANGUAGE", "es")
    monkeypatch.setenv("LC_ALL", "C")

    i18n.setup()

    assert i18n._("Backup failed") == "Error en la copia de seguridad"
    assert i18n._("no repository configured") == "no hay ningún repositorio configurado"


def test_ngettext_selects_plural():
    assert i18n.ngettext("1 file", "{n} files", 1) == "1 file"
    assert i18n.ngettext("1 file", "{n} files", 2) == "{n} files"
