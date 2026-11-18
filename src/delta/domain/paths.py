"""Pure validation of user-supplied paths for restore requests."""

import posixpath

from delta.domain.errors import InvalidPath
from delta.i18n import _


def _outside(label: str, base: str) -> str:
    """Whole sentences, not a translated word dropped into one: the wording depends on the noun."""
    return {
        "source": lambda: _("source must be inside {base}"),
        "target": lambda: _("target must be inside {base}"),
        "path": lambda: _("path must be inside {base}"),
    }[label]().format(base=base)


def _not_absolute(label: str) -> str:
    return {
        "source": lambda: _("source must be an absolute path"),
        "target": lambda: _("target must be an absolute path"),
        "path": lambda: _("path must be an absolute path"),
    }[label]()


def _parent_reference(label: str) -> str:
    return {
        "source": lambda: _("source must not contain '..'"),
        "target": lambda: _("target must not contain '..'"),
        "path": lambda: _("path must not contain '..'"),
    }[label]()


def ensure_within(path: str, root: str, label: str) -> str:
    normalized, base = posixpath.normpath(path), posixpath.normpath(root)
    if normalized != base and not normalized.startswith(base + "/"):
        raise InvalidPath(_outside(label, base))
    return normalized


def _check(path: str, home: str, label: str) -> str:
    if not posixpath.isabs(path):
        raise InvalidPath(_not_absolute(label))
    if ".." in path.split("/"):
        raise InvalidPath(_parent_reference(label))
    return ensure_within(path, home, label)


def validate_in_home(path: str, home: str) -> str:
    return _check(path, home, "path")


def validate_restore(source: str, target: str, home: str) -> tuple[str, str]:
    """Return normalized (source, target); both must live under `home`."""
    return _check(source, home, "source"), _check(target, home, "target")
