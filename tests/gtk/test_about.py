"""The About dialog credits its author and carries the license of Delta and of what it uses."""

from types import SimpleNamespace

from gi.repository import Gtk

from delta import __version__
from delta.ui import about, credits
from delta.ui.about import KNOWN, build_about


def test_the_dialog_names_the_author_with_his_website_and_the_version():
    dialog = build_about()

    assert dialog.get_developer_name() == "Álvaro Castillo"
    assert dialog.get_developers() == ["Álvaro Castillo https://sincorchetes.tech"]
    assert dialog.get_version() == __version__
    assert "Álvaro Castillo" in dialog.get_copyright()


def test_the_dialog_points_to_the_documentation_and_to_where_problems_are_reported():
    dialog = build_about()

    assert dialog.get_website() == "https://delta.sincorchetes.tech"
    assert dialog.get_issue_url() == "https://github.com/sincorchetes/delta/issues"


def test_delta_itself_is_gpl_3_or_later():
    assert build_about().get_license_type() == Gtk.License.GPL_3_0
    assert credits.LICENSE == "GPL-3.0-or-later"


def test_every_license_of_what_delta_uses_can_be_shown(monkeypatch):
    legal = []
    real = about.Adw.AboutDialog

    def recording(**properties):
        """AdwAboutDialog is final (it cannot be subclassed): note the calls on the instance instead."""
        dialog = real(**properties)
        add_legal_section = dialog.add_legal_section

        def note(title, copyright, license_type, license):
            legal.append((title, license_type, license))
            add_legal_section(title, copyright, license_type, license)

        dialog.add_legal_section = note
        return dialog

    monkeypatch.setattr(about, "Adw", SimpleNamespace(AboutDialog=recording))

    build_about()

    assert [title for title, _kind, _text in legal] == [c.name for c in credits.RUNTIME]
    named_ones = {c.name for c in credits.RUNTIME if c.license in KNOWN}
    assert {title for title, kind, _ in legal if kind != Gtk.License.CUSTOM} == named_ones
    custom = [text for _title, kind, text in legal if kind == Gtk.License.CUSTOM]
    assert custom and all("SPDX-License-Identifier" in text for text in custom)
