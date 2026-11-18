"""The ID3v2 tag at the start of an mp3 (title, artist, cover art), which can be cut off. No GTK."""

import shutil

HEADER = 10
FOOTER_FLAG = 0x10


def id3v2_length(header: bytes) -> int:
    """Bytes the ID3v2 tag at the start of a file takes, or 0 when there is none."""
    if len(header) < HEADER or header[:3] != b"ID3":
        return 0
    size_bytes = header[6:10]
    if any(byte & 0x80 for byte in size_bytes):  # the size is 7 bits per byte: this is not a tag
        return 0
    size = (size_bytes[0] << 21) | (size_bytes[1] << 14) | (size_bytes[2] << 7) | size_bytes[3]
    footer = HEADER if header[5] & FOOTER_FLAG else 0
    return HEADER + size + footer


def copy_without_id3v2(source: str, destination: str) -> bool:
    """Write `source` minus its leading ID3v2 tag; False (and nothing written) when it has none.

    The audio is untouched. Only the copy lacks the tag, so the cover art, which makes GStreamer
    1.28 abort on some mp3 files, never reaches the player.
    """
    with open(source, "rb") as original:
        skip = id3v2_length(original.read(HEADER))
        if skip == 0:
            return False
        original.seek(skip)
        with open(destination, "wb") as copy:
            shutil.copyfileobj(original, copy, 1 << 20)
    return True
