"""A test that reads the repository (not only src/, tests/ and po/) cannot run in the mutants folder: mutmut ignores it.

mutmut copies only src/, tests/ and po/, so a test that opens `scripts/`, `CHANGELOG.md` and the like fails when it collects
its stats, and that is only seen in the CI. The convention that finds them is `Path(__file__).resolve().parents[2]`."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests" / "unit"
# Reads only po/, which `also_copy` takes into the mutants folder.
READS_ONLY_COPIED_FILES = {"test_i18n.py"}


def ignored_by_mutmut() -> set[str]:
    options = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["mutmut"]["pytest_add_cli_args"]
    return {Path(option.removeprefix("--ignore=")).name for option in options if option.startswith("--ignore=")}


def test_every_test_that_reads_the_repository_is_ignored_by_the_mutation_tests():
    readers = {p.name for p in TESTS.glob("test_*.py") if "parents[2]" in p.read_text(encoding="utf-8")}

    missing = sorted(readers - ignored_by_mutmut() - READS_ONLY_COPIED_FILES)

    assert not missing, f"add --ignore=tests/unit/<name> to pytest_add_cli_args in [tool.mutmut]: {missing}"


def test_what_is_ignored_still_exists():
    gone = sorted(name for name in ignored_by_mutmut() if not (TESTS / name).exists())

    assert not gone, f"remove from pytest_add_cli_args in [tool.mutmut]: {gone}"
