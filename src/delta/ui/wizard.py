"""The setup wizard's rules and state. No GTK, no D-Bus; the filesystem is injected."""

import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from delta.i18n import _

# No 0/O or 1/I/L: the recovery key may be read from paper.
RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
MIN_OWN_PASSPHRASE = 10


class PathState(str, Enum):
    MISSING = "missing"
    EMPTY_DIR = "empty-dir"
    NOT_EMPTY = "not-empty"
    FILE = "file"
    REPOSITORY = "repository"  # a folder that already holds a backup repository: it can be reopened
    UNMOUNTED = "unmounted"  # inside the place of a drive that is not connected
    READ_ONLY = "read-only"  # on a file system that is mounted so that nothing can be written to it
    NOT_WRITABLE = "not-writable"  # a place the person has no permission to write in


Inspect = Callable[[str], PathState]


class Step(Enum):
    DESTINATION = "destination"
    FOLDERS = "folders"
    RECOVERY = "recovery"
    SUMMARY = "summary"


class Protection(Enum):
    GENERATED = "generated"
    OWN = "own"


@dataclass(frozen=True)
class SetupRequest:
    location: str
    folders: tuple[str, ...]  # empty means the whole home folder
    passphrase: str


def generate_recovery_key() -> str:
    """30 characters in six dash-separated groups (150 bits)."""
    groups = [
        "".join(secrets.choice(RECOVERY_ALPHABET) for _index in range(5)) for _group in range(6)
    ]
    return "-".join(groups)


def _expand(path: str, home: str) -> str:
    return home + path[1:] if path == "~" or path.startswith("~/") else path


def _normal(path: str) -> str:
    return re.sub(r"/+", "/", path).rstrip("/") or "/"


def check_destination(text: str, home: str, inspect: Inspect) -> tuple[str | None, str | None]:
    """(location, None) when usable, else (None, why not)."""
    text = text.strip()
    if not text:
        return None, _("Choose where to keep your backups.")
    path = _normal(_expand(text, home))
    if not path.startswith("/"):
        return None, _("Enter a full folder path, for example ~/Backups.")
    if path == "/":
        return None, _("Choose a folder, not the whole disk.")
    state = inspect(path)
    if state is PathState.FILE:
        return None, _("That path is a file, not a folder.")
    if state is PathState.UNMOUNTED:
        return None, _("That place is on a drive that is not connected. Connect it first.")
    if state is PathState.READ_ONLY:
        return None, _("That place is read-only: nothing can be written to it. Choose another.")
    if state is PathState.NOT_WRITABLE:
        return None, _("You cannot write in that folder. Choose another, or change its permissions.")
    if state is PathState.NOT_EMPTY:
        return None, _("That folder is not empty. Choose a new or empty folder.")
    return path, None


def check_folders(
    entries: tuple[str, ...], home: str, inspect: Inspect
) -> tuple[tuple[str, ...], list[str]]:
    """Normalised, de-duplicated folders and one message per unusable entry."""
    folders, problems = [], []
    for entry in entries:
        path = _normal(_expand(entry.strip(), home))
        if not path.startswith("/"):
            problems.append(_("“{folder}” is not a full path.").format(folder=entry))
            continue
        state = inspect(path)
        if state is PathState.MISSING:
            problems.append(_("“{folder}” does not exist.").format(folder=entry))
        elif state is PathState.FILE:
            problems.append(_("“{folder}” is a file, not a folder.").format(folder=entry))
        elif path not in folders:
            folders.append(path)
    return tuple(folders), problems


def repository_exists(message: str) -> bool:
    """Borg's own (untranslated) refusal to initialise over a repository."""
    return "repository already exists" in message.lower()


def check_passphrase(passphrase: str, confirmation: str) -> str | None:
    if len(passphrase) < MIN_OWN_PASSPHRASE:
        return _("Use at least {n} characters.").format(n=MIN_OWN_PASSPHRASE)
    if passphrase != confirmation:
        return _("The two passphrases do not match.")
    return None


@dataclass
class WizardModel:
    home: str
    inspect: Inspect
    recovery_key: str = field(default_factory=generate_recovery_key)
    step: Step = Step.DESTINATION
    destination: str = ""  # a folder or drive on this computer
    folders: tuple[str, ...] = ()
    protection: Protection = Protection.GENERATED
    own_passphrase: str = ""
    own_confirmation: str = ""
    recovery_saved: bool = False  # saved to a file, copied, or the risk accepted
    keep_folders: bool = False  # changing the destination: what is backed up stays as it is

    @property
    def reuses_repository(self) -> bool:
        """The folder already holds a repository: it is reopened with its passphrase, not created again."""
        location, _error = check_destination(self.destination, self.home, self.inspect)
        return location is not None and self.inspect(location) is PathState.REPOSITORY

    @property
    def steps(self) -> list[Step]:
        skipped = {Step.FOLDERS} if self.keep_folders else set()
        if self.reuses_repository:
            skipped.add(Step.RECOVERY)  # the passphrase is the one it already has
        return [step for step in Step if step not in skipped]

    def destination_text(self) -> str:
        """What the user typed or chose, before it is checked."""
        return self.destination

    @property
    def passphrase(self) -> str:
        return self.recovery_key if self.protection is Protection.GENERATED else self.own_passphrase

    def errors(self, step: Step | None = None) -> list[str]:
        step = step or self.step
        if step is Step.DESTINATION:
            return self._destination_errors()
        if step is Step.FOLDERS:
            return check_folders(self.folders, self.home, self.inspect)[1]
        if step is Step.RECOVERY:
            return self._protection_errors()
        return [e for earlier in self.steps[:-1] for e in self.errors(earlier)]

    def _destination_errors(self) -> list[str]:
        _location, error = check_destination(self.destination, self.home, self.inspect)
        return [error] if error else []

    def _protection_errors(self) -> list[str]:
        if self.protection is Protection.OWN:
            error = check_passphrase(self.own_passphrase, self.own_confirmation)
            return [error] if error else []
        if not self.recovery_saved:
            return [_("Save your recovery key, or confirm that you accept the risk.")]
        return []

    def can_continue(self) -> bool:
        return not self.errors()

    @property
    def is_last(self) -> bool:
        return self.step is Step.SUMMARY

    def next(self) -> bool:
        steps = self.steps
        if self.is_last or not self.can_continue():
            return False
        self.step = steps[steps.index(self.step) + 1]
        return True

    def back(self) -> bool:
        steps = self.steps
        if self.step is steps[0]:
            return False
        self.step = steps[steps.index(self.step) - 1]
        return True

    def request(self) -> SetupRequest:
        location, _error = check_destination(self.destination_text(), self.home, self.inspect)
        problems = self.errors(Step.SUMMARY)
        if location is None or problems:
            raise ValueError(problems[0])
        folders, _problems = check_folders(self.folders, self.home, self.inspect)
        return SetupRequest(location, folders, self.passphrase)

    def summary(self) -> list[tuple[str, str]]:
        location, _error = check_destination(self.destination_text(), self.home, self.inspect)
        folders, _problems = check_folders(self.folders, self.home, self.inspect)
        if self.reuses_repository:
            protection = _("The passphrase it already has")
        elif self.protection is Protection.GENERATED:
            protection = _("Recovery key, saved by you")
        else:
            protection = _("Your own passphrase")
        rows = [(_("Destination"), location or "")]
        if not self.keep_folders:
            rows.append((_("Folders"), ", ".join(folders) or _("Your personal folder")))
        return [*rows, (_("Protection"), protection)]
