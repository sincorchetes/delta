"""The notes of a GitHub Release are the section of CHANGELOG.md of its version."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "release_notes.sh"

CHANGELOG = """# Changelog

## [0.1.10] - 2026-12-01

Ten.

## [0.1.1] - 2026-11-18

No change to the program.

### Fixed

- A thing.

## [0.1.0] - 2026-11-17

The first release.

[0.1.10]: https://example.org/0.1.10
[0.1.1]: https://example.org/0.1.1
[0.1.0]: https://example.org/0.1.0
"""


def notes(version: str, tmp_path: Path, text: str = CHANGELOG) -> subprocess.CompletedProcess:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(text, encoding="utf-8")
    return subprocess.run(["sh", str(SCRIPT), version, str(changelog)], capture_output=True, encoding="utf-8")


def test_the_notes_are_the_section_of_the_version_without_its_heading(tmp_path):
    done = notes("0.1.1", tmp_path)

    assert done.returncode == 0
    assert done.stdout == "No change to the program.\n\n### Fixed\n\n- A thing.\n"


def test_a_version_is_not_taken_for_another_that_starts_the_same(tmp_path):
    assert notes("0.1.10", tmp_path).stdout == "Ten.\n"


def test_the_last_section_does_not_carry_the_links_of_the_end_of_the_file(tmp_path):
    assert notes("0.1.0", tmp_path).stdout == "The first release.\n"


def test_a_version_without_a_section_fails(tmp_path):
    done = notes("9.9.9", tmp_path)

    assert done.returncode == 1 and done.stdout == "" and "no section for 9.9.9" in done.stderr


def test_the_version_of_the_build_has_notes_in_the_real_changelog():
    found = re.search(r"^\s+version: '([^']+)',", (ROOT / "meson.build").read_text(encoding="utf-8"), re.M)
    assert found is not None
    changelog = ROOT / "CHANGELOG.md"
    done = subprocess.run(["sh", str(SCRIPT), found.group(1), str(changelog)], capture_output=True, encoding="utf-8")

    assert done.returncode == 0 and done.stdout.strip() and "## [" not in done.stdout
