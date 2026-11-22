"""A version tag is only published when the tree it points to says that version."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "check_tag.sh"

CHANGELOG = """# Changelog

## [Unreleased]

## [0.2.0] - 2026-11-20

### Added

- Something.

## [0.1.3] - 2026-11-20

- Older.
"""


def tree(tmp_path, version="0.2.0", changelog=CHANGELOG):
    (tmp_path / "meson.build").write_text(f"project(\n  'delta',\n  version: '{version}',\n  license: 'GPL-3.0-or-later',\n)\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


def check(tag, where):
    return subprocess.run(["sh", str(SCRIPT), tag, str(where)], capture_output=True, encoding="utf-8")


def test_a_tag_that_says_what_the_tree_says_passes(tmp_path):
    done = check("v0.2.0", tree(tmp_path))

    assert done.returncode == 0 and "v0.2.0 matches meson.build and CHANGELOG.md" in done.stdout


def test_a_tag_pushed_before_the_version_was_raised_is_refused_and_says_what_to_do(tmp_path):
    done = check("v0.2.0", tree(tmp_path, version="0.1.3"))

    assert done.returncode == 1
    assert "the tag is v0.2.0 and meson.build says '0.1.3'" in done.stderr
    assert "merge the pull request that raises the version before pushing the tag" in done.stderr


def test_a_tree_without_a_version_is_refused(tmp_path):
    (tmp_path / "meson.build").write_text("project('delta')\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")

    done = check("v0.2.0", tmp_path)

    assert done.returncode == 1 and "meson.build says 'nothing'" in done.stderr


def test_a_version_without_notes_is_refused(tmp_path):
    done = check("v0.2.0", tree(tmp_path, changelog="# Changelog\n\n## [Unreleased]\n\n## [0.1.3] - 2026-11-20\n\n- Older.\n"))

    assert done.returncode == 1 and "CHANGELOG.md has no section for 0.2.0" in done.stderr


@pytest.mark.parametrize("tag", ["0.2.0", "release-0.2.0", "v0.2", "v0.2.0.1", "v0.2.0-rc1", "v0.2.x", "vfoo"])
def test_what_is_not_a_version_tag_is_refused(tmp_path, tag):
    done = check(tag, tree(tmp_path))

    assert done.returncode == 1 and "is not" in done.stderr


def test_the_real_tree_passes_with_its_own_version():
    meson = (ROOT / "meson.build").read_text(encoding="utf-8")
    version = re.search(r"^\s+version: '([^']+)',", meson, re.M).group(1)

    assert check(f"v{version}", ROOT).returncode == 0
