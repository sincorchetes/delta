"""What the version window can show of a version, decided from its type and size. No GTK."""

from enum import Enum

AUTO_IMAGE_MAX = 50_000_000  # bigger files ask before being unpacked just to be looked at
AUTO_TEXT_MAX = 2_000_000
AUTO_MEDIA_MAX = 300_000_000  # a video has to be unpacked whole before it can be played
TEXT_SHOWN_BYTES = 64_000  # a preview is a glance, not an editor

TEXT_TYPES = frozenset(
    {
        "application/json",
        "application/xml",
        "application/x-shellscript",
        "application/x-yaml",
        "application/toml",
        "application/javascript",
        "application/x-desktop",
    }
)


# GStreamer 1.28.8 aborts the whole process (decodebin3 assertion, not catchable) on an .mp3
# whose ID3v2 tag carries cover art; ogg, flac, wav and an m4a with cover art play fine. The
# player is given a copy of these without that tag (see ui/id3.py). Verified with such a file.
MP3_TYPES = frozenset({"audio/mpeg", "audio/mp3", "audio/x-mp3", "audio/x-mpeg"})


def needs_untagged_copy(mime: str) -> bool:
    return mime in MP3_TYPES


class Kind(Enum):
    IMAGE = "image"
    TEXT = "text"
    VIDEO = "video"
    AUDIO = "audio"
    FOLDER = "folder"
    OTHER = "other"  # shown with its own application, not inside the window


def kind_of(mime: str, is_dir: bool) -> Kind:
    if is_dir:
        return Kind.FOLDER
    if mime.startswith("image/"):
        return Kind.IMAGE
    if mime.startswith("video/"):
        return Kind.VIDEO
    if mime.startswith("audio/"):
        return Kind.AUDIO
    if mime.startswith("text/") or mime in TEXT_TYPES:
        return Kind.TEXT
    return Kind.OTHER


def icon_for(mime: str) -> str:
    """A symbolic icon that says what kind of file this is (never a folder)."""
    for prefix, icon in (
        ("audio/", "audio-x-generic-symbolic"),
        ("video/", "video-x-generic-symbolic"),
        ("image/", "image-x-generic-symbolic"),
    ):
        if mime.startswith(prefix):
            return icon
    return "text-x-generic-symbolic"


def needs_confirmation(kind: Kind, size: int) -> bool:
    """Unpacking a big file only to glance at it is slow: let the user decide."""
    limits = {
        Kind.IMAGE: AUTO_IMAGE_MAX,
        Kind.TEXT: AUTO_TEXT_MAX,
        Kind.VIDEO: AUTO_MEDIA_MAX,
        Kind.AUDIO: AUTO_MEDIA_MAX,
    }
    limit = limits.get(kind)
    return limit is not None and size > limit


def looks_binary(chunk: bytes) -> bool:
    """A NUL byte never appears in text, whatever its extension claimed."""
    return b"\0" in chunk
