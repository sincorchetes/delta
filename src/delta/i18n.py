"""gettext helpers; every user-visible string goes through `_()`."""

import gettext
import locale
import os

DOMAIN = "delta"


def _localedir() -> str | None:
    return os.environ.get("DELTA_LOCALEDIR") or None


def setup() -> None:
    """Bind the translation domain for this process (call once at startup)."""
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass  # LANG names a locale that is not generated: fall back to untranslated text
    for module in (locale, gettext):
        module.bindtextdomain(DOMAIN, _localedir())
    gettext.textdomain(DOMAIN)


def _(message: str) -> str:
    return gettext.dgettext(DOMAIN, message)


def ngettext(singular: str, plural: str, n: int) -> str:
    return gettext.dngettext(DOMAIN, singular, plural, n)
