"""The Flatpak manifest says what the code needs from the sandbox, and no more.

Read as text: the manifest is simple, and a YAML library would be one more dependency for the tests.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP_ID = "io.github.sincorchetes.Delta"
TEXT = (ROOT / "flatpak" / f"{APP_ID}.yaml").read_text(encoding="utf-8")


def top_level(key: str) -> str:
    return re.search(rf"^{re.escape(key)}:\s*(.+)$", TEXT, re.M).group(1).strip()


def finish_args(text: str) -> list[str]:
    return re.findall(r"^  - (--[^\s#]+)", text.split("finish-args:")[1].split("modules:")[0], re.M)


FINISH_ARGS = finish_args(TEXT)


def test_the_application_is_the_one_of_the_desktop_entry_and_the_metadata():
    assert top_level("app-id") == APP_ID and (ROOT / "data" / f"{APP_ID}.desktop.in").exists()
    assert top_level("command") == "delta-ui" and (ROOT / "src" / "delta-ui").exists()


def test_what_a_sandbox_cannot_have_is_left_out_of_the_install():
    assert "- -Dsystemd_units=false" in TEXT and "- -Dnautilus_extension=false" in TEXT


@pytest.mark.parametrize("not_to_copy", [".git", ".devenv", ".flatpak-builder", "build-flatpak", "build", "website"])
def test_the_source_copy_leaves_out_what_a_working_copy_holds_besides_the_code(not_to_copy):
    skipped = TEXT.split("skip:")[1].split("post-install:")[0]

    assert f"- {not_to_copy}\n" in skipped


def test_the_daemon_is_a_command_of_the_sandbox_for_the_background_portal_to_start():
    assert re.search(r"^\s+- ln -sf \.\./libexec/delta-daemon /app/bin/delta-daemon$", TEXT, re.M)


def test_the_translations_stay_in_the_application_for_the_nautilus_extension_to_read():
    assert top_level("separate-locales") == "false"


def test_the_translations_are_found_in_the_sandbox():
    assert "--env=DELTA_LOCALEDIR=/app/share/locale" in FINISH_ARGS


def test_the_window_and_the_daemon_share_their_settings_through_a_file():
    # Two processes, and the sandbox has no dconf: in memory each would see only what it wrote itself.
    assert "--env=GSETTINGS_BACKEND=keyfile" in FINISH_ARGS


def test_the_permissions_are_the_ones_a_backup_program_needs_and_nothing_wider():
    granted = [arg for arg in FINISH_ARGS if not arg.startswith("--env=")]

    assert sorted(granted) == sorted(
        [
            "--share=ipc",
            "--socket=wayland",
            "--socket=fallback-x11",
            "--device=dri",
            "--filesystem=home",
            "--filesystem=/run/media",
        ]
    )


@pytest.mark.parametrize("wider", ["--filesystem=host", "--filesystem=host-os", "--socket=session-bus", "--device=all"])
def test_no_wider_permission_is_asked_for(wider):
    assert wider not in FINISH_ARGS


def test_borg_is_part_of_the_sandbox_since_the_computers_one_cannot_be_reached():
    assert "- python3-borgbackup.json" in TEXT


def test_borg_comes_from_pinned_sources_so_that_the_build_needs_no_network():
    module = (ROOT / "flatpak" / "python3-borgbackup.json").read_text(encoding="utf-8")

    assert "--share=network" not in TEXT and "--share=network" not in module
    assert module.count('"type": "file"') == module.count('"sha256"') > 0
