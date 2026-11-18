import pytest

from delta.ui.preview_kind import (
    AUTO_IMAGE_MAX,
    AUTO_MEDIA_MAX,
    AUTO_TEXT_MAX,
    Kind,
    icon_for,
    kind_of,
    looks_binary,
    needs_confirmation,
    needs_untagged_copy,
)


@pytest.mark.parametrize(
    ("mime", "expected"),
    [
        ("image/jpeg", Kind.IMAGE),
        ("image/png", Kind.IMAGE),
        ("text/plain", Kind.TEXT),
        ("text/x-python", Kind.TEXT),
        ("application/json", Kind.TEXT),
        ("application/pdf", Kind.OTHER),
        ("video/mp4", Kind.VIDEO),
        ("video/webm", Kind.VIDEO),
        ("audio/flac", Kind.AUDIO),
        ("audio/ogg", Kind.AUDIO),
        ("audio/mp4", Kind.AUDIO),
        ("audio/mpeg", Kind.AUDIO),
        ("audio/x-mp3", Kind.AUDIO),
        ("application/octet-stream", Kind.OTHER),
        ("", Kind.OTHER),
    ],
)
def test_a_file_is_classified_by_its_content_type(mime, expected):
    assert kind_of(mime, is_dir=False) is expected


@pytest.mark.parametrize(
    ("mime", "icon"),
    [
        ("audio/mpeg", "audio-x-generic-symbolic"),
        ("video/mp4", "video-x-generic-symbolic"),
        ("image/png", "image-x-generic-symbolic"),
        ("application/pdf", "text-x-generic-symbolic"),
        ("", "text-x-generic-symbolic"),
    ],
)
def test_the_icon_says_what_kind_of_file_it_is(mime, icon):
    assert icon_for(mime) == icon
    assert "folder" not in icon_for(mime)


@pytest.mark.parametrize(
    ("mime", "expected"),
    [
        ("audio/mpeg", True),
        ("audio/mp3", True),
        ("audio/x-mp3", True),
        ("audio/ogg", False),
        ("audio/flac", False),
        ("audio/mp4", False),
        ("video/mp4", False),
        ("", False),
    ],
)
def test_only_mp3_is_played_from_a_copy_without_its_tag(mime, expected):
    assert needs_untagged_copy(mime) is expected


def test_a_folder_is_a_folder_whatever_its_type():
    assert kind_of("image/png", is_dir=True) is Kind.FOLDER


@pytest.mark.parametrize(
    ("kind", "size", "ask"),
    [
        (Kind.IMAGE, AUTO_IMAGE_MAX, False),
        (Kind.IMAGE, AUTO_IMAGE_MAX + 1, True),
        (Kind.TEXT, AUTO_TEXT_MAX, False),
        (Kind.TEXT, AUTO_TEXT_MAX + 1, True),
        (Kind.VIDEO, AUTO_MEDIA_MAX, False),
        (Kind.VIDEO, AUTO_MEDIA_MAX + 1, True),
        (Kind.AUDIO, AUTO_MEDIA_MAX + 1, True),
        (Kind.OTHER, 10**12, False),
        (Kind.FOLDER, 10**12, False),
    ],
)
def test_only_big_images_texts_and_media_ask_before_being_unpacked(kind, size, ask):
    assert needs_confirmation(kind, size) is ask


def test_a_nul_byte_means_binary():
    assert looks_binary(b"MZ\x90\0\x03")
    assert not looks_binary("hola, señor".encode())
