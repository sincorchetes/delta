"""Every workflow is valid YAML with what GitHub needs: one that is not shows up there as an empty run that failed, with no log."""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")  # a development dependency (uv.lock): the distributions test with what their packaging ships

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def test_there_are_workflows_to_look_at():
    assert len(WORKFLOWS) >= 6


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda path: path.name)
def test_a_workflow_is_valid_yaml_with_a_name_triggers_and_jobs(workflow):
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))

    assert isinstance(document, dict)
    assert document.get("name")
    assert document.get(True) or document.get("on"), "no triggers"  # YAML reads a bare `on` as the boolean True
    assert document.get("jobs")


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda path: path.name)
def test_every_job_has_a_runner_and_steps(workflow):
    jobs = yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"]

    for name, job in jobs.items():
        assert "runs-on" in job or "uses" in job, name
        assert job.get("steps") or "uses" in job, name
