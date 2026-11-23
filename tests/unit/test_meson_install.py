"""The package is installed without the bytecode that a working copy leaves in every one of its folders."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "delta"


def excluded() -> set[str]:
    text = (ROOT / "src" / "meson.build").read_text(encoding="utf-8")
    block = re.search(r"exclude_directories:\s*\[(.*?)\]", text, re.S)
    assert block is not None
    return set(re.findall(r"'([^']+)'", block.group(1)))


def test_every_folder_of_the_package_has_its_bytecode_left_out():
    folders = [path.parent.relative_to(PACKAGE) for path in PACKAGE.rglob("__init__.py") if "__pycache__" not in path.parts]
    wanted = {"__pycache__"} | {f"{folder.as_posix()}/__pycache__" for folder in folders if folder.as_posix() != "."}

    assert len(wanted) > 1  # there are subpackages to look at
    assert wanted <= excluded()
