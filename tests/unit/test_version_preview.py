"""What the pane of a version unpacks, shows and plays: images, text, video and audio."""

import pytest
from version_preview_support import AUDIO, FakeMedia, Setup, TAG, play_mp3, unpack_video


def test_a_small_image_is_unpacked_and_then_shown_inside_the_window():
    s = Setup()
    s.select(s.target("a"))

    assert s.pane.events == [("loading",)] and s.client.requests == [("a", "/home/u/photo.jpg")]
    s.finish("j1", message="/run/preview/a/photo.jpg")

    assert s.pane.events[-1] == ("image", "/run/preview/a/photo.jpg")


def test_a_text_file_is_shown_as_text():
    s = Setup("/home/u/notes.txt")
    s.select(s.target("a"))
    s.finish("j1", message="/run/preview/a/notes.txt")
    assert s.pane.events[-1] == ("text", "/run/preview/a/notes.txt")


def test_a_file_inside_a_folder_is_unpacked_by_its_own_path():
    s = Setup("/home/u/Pictures")
    inside = s.target("a", path="/home/u/Pictures/sub/me.png")

    s.select(inside)

    assert s.client.requests == [("a", "/home/u/Pictures/sub/me.png")]
    s.finish("j1", message="/run/preview/a/me.png")
    assert s.pane.events[-1] == ("image", "/run/preview/a/me.png")


def test_two_files_of_one_snapshot_are_not_mistaken_for_each_other():
    s = Setup("/home/u/Pictures")
    one, two = s.target("a", path="/home/u/Pictures/1.png"), s.target("a", path="/home/u/Pictures/2.png")
    s.select(one)
    s.finish("j1", message="/run/preview/a/1.png")

    s.select(two)

    assert s.client.requests == [("a", "/home/u/Pictures/1.png"), ("a", "/home/u/Pictures/2.png")]


@pytest.mark.parametrize("name", ["clip.mp4", "song.flac", "voice.ogg"])
def test_video_and_audio_are_unpacked_and_given_to_the_player(name):
    s = Setup(f"/home/u/{name}")
    s.select(s.target("a"))
    s.finish("j1", message=f"/run/preview/a/{name}")
    assert s.pane.events[-1] == ("media", f"/run/preview/a/{name}")


def test_an_mp3_with_cover_art_is_played_from_a_copy_without_its_tag(tmp_path):
    s, unpacked = play_mp3(tmp_path, TAG + AUDIO)

    kind, played = s.pane.events[-1]

    assert kind == "media" and played != str(unpacked)
    assert open(played, "rb").read() == AUDIO
    assert unpacked.read_bytes() == TAG + AUDIO  # the unpacked version itself is untouched


def test_an_mp3_without_a_tag_is_played_as_it_is(tmp_path):
    s, unpacked = play_mp3(tmp_path, AUDIO)
    assert s.pane.events[-1] == ("media", str(unpacked))


def test_the_copies_made_for_the_player_are_removed_on_close(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    s, _ = play_mp3(tmp_path, TAG + AUDIO, scratch)
    assert any(scratch.iterdir())

    s.previewer.close()

    assert not any(scratch.iterdir())


def test_when_the_copy_cannot_be_made_the_mp3_goes_to_its_own_application(tmp_path):
    s, unpacked = play_mp3(tmp_path, TAG + AUDIO, scratch=tmp_path / "missing")
    assert s.pane.events[-1][0] == "action" and ("media", str(unpacked)) not in s.pane.events


def test_where_the_player_cannot_be_made_a_video_goes_to_its_own_application():
    # GTK ends the whole program when GStreamer cannot make it, so it must not be tried in this process.
    s = Setup("/home/u/film.mp4", media=FakeMedia(supported=False))

    unpack_video(s)

    assert s.pane.events[-1][0] == "action" and not any(event[0] == "media" for event in s.pane.events)


def test_an_mp3_is_not_even_copied_when_there_is_no_player_for_it(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    unpacked = tmp_path / "unpacked.mp3"
    unpacked.write_bytes(TAG + AUDIO)
    s = Setup("/home/u/song.mp3", scratch_root=str(scratch), media=FakeMedia(supported=False))

    s.select(s.target("a"))
    s.finish("j1", message=str(unpacked))

    assert s.pane.events[-1][0] == "action" and not any(scratch.iterdir())


def test_a_video_waits_for_the_answer_about_the_player_and_then_plays():
    media = FakeMedia(supported=None)
    s = Setup("/home/u/film.mp4", media=media)
    unpack_video(s)
    assert s.pane.events == [("loading",)]  # still the spinner: the answer has not come

    media.answer(True)

    assert s.pane.events[-1] == ("media", "/run/preview/a/film.mp4")


def test_a_video_waits_for_the_answer_and_then_goes_to_its_own_application_when_there_is_no_player():
    media = FakeMedia(supported=None)
    s = Setup("/home/u/film.mp4", media=media)
    unpack_video(s)

    media.answer(False)

    assert s.pane.events[-1][0] == "action" and not any(event[0] == "media" for event in s.pane.events)


def test_if_another_version_is_chosen_while_the_player_is_tried_the_answer_shows_nothing():
    media = FakeMedia(supported=None)
    s = Setup("/home/u/film.mp4", media=media)
    unpack_video(s)
    s.current = s.target("b")  # the choice changed while the other process was running
    before = list(s.pane.events)

    media.answer(True)

    assert s.pane.events == before
