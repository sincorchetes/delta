"""Where backups live and how they are protected."""

from dataclasses import dataclass
from enum import Enum

from delta.i18n import _


class Encryption(str, Enum):
    NONE = "none"
    REPOKEY_BLAKE2 = "repokey-blake2"


@dataclass(frozen=True)
class Repository:
    location: str
    encryption: Encryption = Encryption.REPOKEY_BLAKE2

    def __post_init__(self) -> None:
        if not self.location:
            raise ValueError(_("repository location must not be empty"))
        if not self.location.startswith("/"):
            raise ValueError(_("repository location must be an absolute path"))
