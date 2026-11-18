"""The «About Delta» dialog: author, co-author, license, and the licenses of what Delta uses."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from delta import __version__
from delta.i18n import _
from delta.ui import credits

# The licenses GTK can show by name; any other expression is shown as written, with its link.
KNOWN = {
    "GPL-3.0-or-later": Gtk.License.GPL_3_0,
    "GPL-2.0-or-later": Gtk.License.GPL_2_0,
    "LGPL-2.1-or-later": Gtk.License.LGPL_2_1,
    "BSD-3-Clause": Gtk.License.BSD_3,
    "MIT": Gtk.License.MIT_X11,
    "Apache-2.0": Gtk.License.APACHE_2_0,
}


def build_about() -> Adw.AboutDialog:
    dialog = Adw.AboutDialog(
        application_name=_("Delta"),
        application_icon="io.github.sincorchetes.Delta",
        developer_name=credits.AUTHOR,
        version=__version__,
        website=credits.DOCUMENTATION,
        issue_url=f"{credits.REPOSITORY}/issues",
        comments=_("File time travel for GNOME, powered by BorgBackup."),
        copyright=credits.COPYRIGHT,
        license_type=KNOWN[credits.LICENSE],
        developers=[f"{credits.AUTHOR} {credits.WEBSITE}"],
        translator_credits=_("translator-credits"),
    )
    dialog.add_link(_("Source code"), credits.REPOSITORY)
    dialog.add_credit_section(_("Co-author"), [f"{credits.CO_AUTHOR} {credits.CO_AUTHOR_URL}"])
    for component in credits.RUNTIME:
        kind = KNOWN.get(component.license, Gtk.License.CUSTOM)
        text = f'<a href="{component.url}">{component.url}</a>\nSPDX-License-Identifier: {component.license}'
        dialog.add_legal_section(component.name, None, kind, text if kind == Gtk.License.CUSTOM else None)
    return dialog
