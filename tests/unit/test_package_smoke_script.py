"""The smoke of a published package waits for the Build Service, so every try has to take the newest version there is."""

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "package_smoke.sh"


def test_the_rpm_distributions_upgrade_the_package_on_every_try():
    line = next(line for line in SCRIPT.read_text().splitlines() if line.strip().startswith("fedora | el)"))

    assert "dnf -y install delta-backup" in line and line.index("dnf -y upgrade delta-backup") > line.index("dnf -y install")


def test_the_installed_package_opens_its_window_under_a_virtual_display():
    text = SCRIPT.read_text()

    assert 'xvfb-run -a python3 "$smoke" /usr --window' in text
    assert 'xwfb-run -- python3 "$smoke" /usr --window' in text
    assert text.index("install_display\n") < text.index("xvfb-run -a")
