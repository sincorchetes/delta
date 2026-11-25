"""The smoke of a published package waits for the Build Service, so every try has to take the newest version there is."""

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "package_smoke.sh"


def test_the_rpm_distributions_upgrade_the_package_on_every_try():
    line = next(line for line in SCRIPT.read_text().splitlines() if line.strip().startswith("fedora | el)"))

    assert "dnf -y install delta-backup" in line and line.index("dnf -y upgrade delta-backup") > line.index("dnf -y install")
