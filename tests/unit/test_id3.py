import pytest

from delta.ui.id3 import copy_without_id3v2, id3v2_length

AUDIO = b"\xff\xfb\x90\x00" + b"audio-frames" * 50


def syncsafe(size):
    return bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F])


def tag(size, flags=0):
    return b"ID3\x03\x00" + bytes([flags]) + syncsafe(size) + b"\x55" * size


def test_the_tag_length_counts_its_header_and_body():
    assert id3v2_length(tag(300)[:10]) == 310


def test_a_size_is_read_seven_bits_per_byte():
    assert id3v2_length(b"ID3\x04\x00\x00" + syncsafe(0x1FFFFF)) == 10 + 0x1FFFFF


def test_a_footer_adds_ten_bytes():
    assert id3v2_length(tag(40, flags=0x10)[:10]) == 10 + 40 + 10


@pytest.mark.parametrize(
    "header",
    [b"", b"ID3", b"\xff\xfb\x90\x00" * 3, b"ID3\x03\x00\x00\xff\xff\xff\xff"],
    ids=["empty", "truncated", "no tag", "size is not syncsafe"],
)
def test_something_that_is_not_a_tag_has_length_zero(header):
    assert id3v2_length(header) == 0


def test_the_copy_is_the_audio_alone(tmp_path):
    source, copy = tmp_path / "song.mp3", tmp_path / "copy.mp3"
    source.write_bytes(tag(5000) + AUDIO)

    assert copy_without_id3v2(str(source), str(copy)) is True

    assert copy.read_bytes() == AUDIO


def test_the_original_is_never_changed(tmp_path):
    source, copy = tmp_path / "song.mp3", tmp_path / "copy.mp3"
    original = tag(100) + AUDIO
    source.write_bytes(original)

    copy_without_id3v2(str(source), str(copy))

    assert source.read_bytes() == original


def test_a_file_without_a_tag_writes_nothing(tmp_path):
    source, copy = tmp_path / "song.mp3", tmp_path / "copy.mp3"
    source.write_bytes(AUDIO)

    assert copy_without_id3v2(str(source), str(copy)) is False

    assert not copy.exists()


def test_a_tag_with_a_footer_is_cut_whole(tmp_path):
    source, copy = tmp_path / "song.mp3", tmp_path / "copy.mp3"
    source.write_bytes(tag(40, flags=0x10) + b"\x33" * 10 + AUDIO)  # 10 more bytes: the footer

    copy_without_id3v2(str(source), str(copy))

    assert copy.read_bytes() == AUDIO
