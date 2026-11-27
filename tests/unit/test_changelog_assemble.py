"""Each change writes its entry in changelog.d/; the version pull request gathers them into CHANGELOG.md."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "changelog_assemble.sh"
NOTES = ROOT / "scripts" / "ci" / "release_notes.sh"
KINDS = "added|changed|deprecated|removed|fixed|security"

CHANGELOG = """# Changelog

Intro.

## [Unreleased]

## [0.4.0] - 2026-11-25

### Added

- Old.
"""


def world(tmp_path: Path, fragments: dict[str, str], changelog: str = CHANGELOG) -> Path:
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    for name, text in fragments.items():
        (tmp_path / "changelog.d" / name).write_text(text, encoding="utf-8")
    return tmp_path


def assemble(root: Path, version: str = "0.5.0", date: str = "2026-12-01") -> subprocess.CompletedProcess:
    return subprocess.run(["sh", str(SCRIPT), version, date, str(root)], capture_output=True, encoding="utf-8")


def test_the_fragments_become_the_section_of_the_version_grouped_by_kind(tmp_path):
    root = world(
        tmp_path,
        {
            "b-thing.fixed.md": "- **Fixed b.** Text\n  goes on.\n",
            "a-thing.added.md": "- **Added a.**\n",
            "c-thing.added.md": "- **Added c.**\n",
            "d-thing.security.md": "- **Secure d.**\n",
            "README.md": "How it works.\n",
        },
    )

    done = assemble(root)

    assert done.returncode == 0, done.stderr
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8") == (
        "# Changelog\n\nIntro.\n\n## [Unreleased]\n\n## [0.5.0] - 2026-12-01\n\n"
        "### Added\n\n- **Added a.**\n\n- **Added c.**\n\n"
        "### Fixed\n\n- **Fixed b.** Text\n  goes on.\n\n"
        "### Security\n\n- **Secure d.**\n\n"
        "## [0.4.0] - 2026-11-25\n\n### Added\n\n- Old.\n"
    )


def test_the_fragments_are_deleted_and_the_explanation_stays(tmp_path):
    root = world(tmp_path, {"a.added.md": "- **A.**\n", "README.md": "How it works.\n"})

    assemble(root)

    assert [p.name for p in (root / "changelog.d").iterdir()] == ["README.md"]


def test_the_notes_of_the_new_version_are_what_the_release_publishes(tmp_path):
    root = world(tmp_path, {"a.added.md": "- **A.**\n", "b.changed.md": "- **B.**\n"})
    assemble(root)

    done = subprocess.run(["sh", str(NOTES), "0.5.0", str(root / "CHANGELOG.md")], capture_output=True, encoding="utf-8")

    assert done.stdout == "### Added\n\n- **A.**\n\n### Changed\n\n- **B.**\n"


def test_today_is_the_date_when_none_is_given(tmp_path):
    root = world(tmp_path, {"a.added.md": "- **A.**\n"})

    done = subprocess.run(["sh", str(SCRIPT), "0.5.0", "", str(root)], capture_output=True, encoding="utf-8")

    assert done.returncode == 0, done.stderr
    assert re.search(r"^## \[0\.5\.0\] - \d{4}-\d\d-\d\d$", (root / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)


@pytest.mark.parametrize(
    ("fragments", "changelog", "message"),
    [
        ({}, CHANGELOG, "no fragments"),
        ({"README.md": "x"}, CHANGELOG, "no fragments"),
        ({"a.added.md": "- A.\n"}, CHANGELOG.replace("- Old.", "- Old.\n\n## [0.5.0] - 2026-11-30\n"), "already has a section"),
        ({"a.added.md": "- A.\n"}, CHANGELOG.replace("## [Unreleased]\n", "## [Unreleased]\n\n- Text left here.\n"), "text of its own"),
        ({"a.added.md": "- A.\n"}, CHANGELOG.replace("## [Unreleased]\n\n", ""), "no [Unreleased] heading"),
        ({"a.added.md": "- A.\n", "b.fixes.md": "- B.\n"}, CHANGELOG, "is not named <name>.<kind>.md"),
        ({"a.added.md": "- A.\n", "noted.md": "- B.\n"}, CHANGELOG, "is not named <name>.<kind>.md"),
    ],
)
def test_what_cannot_be_gathered_is_refused_and_nothing_is_changed(tmp_path, fragments, changelog, message):
    root = world(tmp_path, fragments, changelog)

    done = assemble(root)

    assert done.returncode == 1 and message in done.stderr
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8") == changelog
    assert sorted(p.name for p in (root / "changelog.d").iterdir()) == sorted(fragments)


def test_the_real_fragments_can_be_gathered(tmp_path):
    """The version pull request must find the fragments of this repository ready to be assembled."""
    if not [p for p in (ROOT / "changelog.d").glob("*.md") if p.name != "README.md"]:
        pytest.skip("no fragment waits for a version (the right state just after a release)")
    shutil.copytree(ROOT / "changelog.d", tmp_path / "changelog.d")
    shutil.copy(ROOT / "CHANGELOG.md", tmp_path / "CHANGELOG.md")

    done = assemble(tmp_path, "99.0.0")

    assert done.returncode == 0, done.stderr
    notes = subprocess.run(["sh", str(NOTES), "99.0.0", str(tmp_path / "CHANGELOG.md")], capture_output=True, encoding="utf-8")
    assert notes.returncode == 0 and notes.stdout.startswith("### ")


def test_every_real_fragment_is_one_named_entry():
    fragments = sorted(p for p in (ROOT / "changelog.d").glob("*.md") if p.name != "README.md")

    for fragment in fragments:
        text = fragment.read_text(encoding="utf-8")
        assert re.fullmatch(rf"[a-z0-9-]+\.({KINDS})\.md", fragment.name), fragment.name
        assert text.startswith("- **") and text.endswith("\n"), fragment.name
        assert "\n\n" not in text, f"{fragment.name}: one entry, with no blank line inside"
