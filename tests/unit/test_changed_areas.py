"""The pipeline of the website runs only for the website, and the rest only for what is not the website."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "changed_areas.sh"


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.org", *args], cwd=repo, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def areas(tmp_path: Path, changed: dict[str, str]) -> dict[str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "README.md").write_text("first", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "first")
    before = git(repo, "rev-parse", "HEAD")
    for name, text in changed.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change", "--allow-empty")
    after = git(repo, "rev-parse", "HEAD")
    done = subprocess.run(["sh", str(SCRIPT), before, after], cwd=repo, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return dict(line.split("=") for line in done.stdout.split())


@pytest.mark.parametrize(
    "changed",
    [{"src/delta/x.py": "x"}, {"README.md": "second"}, {"packaging/obs/_service": "x"}, {"scripts/ci/a.sh": "x"}],
)
def test_a_change_outside_the_website_needs_the_tests_and_not_the_website(tmp_path, changed):
    assert areas(tmp_path, changed) == {"code": "true", "web": "false"}


def test_a_change_in_the_website_needs_only_the_website(tmp_path):
    assert areas(tmp_path, {"website/src/content/docs/install.mdx": "x"}) == {"code": "false", "web": "true"}


def test_a_change_in_both_needs_both(tmp_path):
    assert areas(tmp_path, {"website/package.json": "x", "src/delta/x.py": "x"}) == {"code": "true", "web": "true"}


def test_the_workflow_that_builds_the_website_needs_both_to_be_tried(tmp_path):
    assert areas(tmp_path, {".github/workflows/ci.yml": "x"}) == {"code": "true", "web": "true"}


def test_a_change_with_no_files_needs_nothing(tmp_path):
    assert areas(tmp_path, {}) == {"code": "false", "web": "false"}


def test_a_base_that_cannot_be_compared_runs_everything(tmp_path):
    done = subprocess.run(["sh", str(SCRIPT), "0" * 40, "HEAD"], cwd=tmp_path, capture_output=True, text=True)

    assert done.returncode == 0 and done.stdout.split() == ["code=true", "web=true"]
