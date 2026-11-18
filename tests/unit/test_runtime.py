from delta.infrastructure.runtime import FLATPAK_MARKER, in_flatpak


def test_a_sandbox_is_told_by_the_file_flatpak_puts_in_it(tmp_path):
    marker = tmp_path / ".flatpak-info"

    assert in_flatpak(str(marker)) is False
    marker.write_text("[Application]\n")
    assert in_flatpak(str(marker)) is True


def test_the_marker_is_the_one_flatpak_documents():
    assert FLATPAK_MARKER == "/.flatpak-info"
