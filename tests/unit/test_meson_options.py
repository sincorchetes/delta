"""What a Flatpak leaves out of the install: the systemd units and the Nautilus extension, by meson options."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def options() -> dict[str, str]:
    text = (ROOT / "meson_options.txt").read_text(encoding="utf-8")
    return {name: block for name, block in re.findall(r"option\(\s*'([^']+)',(.*?)\n\)", text, re.S)}


def test_both_options_exist_are_booleans_and_default_to_installing():
    found = options()

    assert set(found) == {"systemd_units", "nautilus_extension"}
    for block in found.values():
        assert "type: 'boolean'" in block and "value: true" in block


def test_every_systemd_unit_is_installed_only_when_the_option_is_on():
    meson = (ROOT / "data" / "meson.build").read_text(encoding="utf-8")

    for unit in ("systemd/delta.service.in", "systemd/delta-backup.service.in", "systemd/delta.timer"):
        before = meson[: meson.index(unit)]
        assert "if get_option('systemd_units')" in before, unit
        assert before.rindex("if get_option('systemd_units')") > before.rfind("endif"), unit  # still open there


def test_the_bus_service_file_points_to_systemd_only_when_the_units_are_installed():
    service = (ROOT / "data" / "io.github.sincorchetes.Delta.Service1.service.in").read_text(encoding="utf-8")
    meson = (ROOT / "data" / "meson.build").read_text(encoding="utf-8")

    assert "SystemdService" not in service and "@systemd_service@" in service
    assert "get_option('systemd_units') ? 'SystemdService=delta.service' : ''" in meson


def test_the_nix_package_copies_every_file_and_folder_the_meson_build_needs():
    """Nix builds from a list of sources: one that is missing fails there, not here (meson_options.txt, help/)."""
    nix = (ROOT / "nix" / "package.nix").read_text(encoding="utf-8")
    listed = set(re.findall(r"^\s+\.\./([\w.]+)$", nix.split("fileset = lib.fileset.unions [")[1].split("]")[0], re.M))

    needed = {"meson.build", "meson_options.txt", "data", "help", "po", "src"}
    assert needed <= listed, needed - listed
    for name in needed:
        assert (ROOT / name).exists(), name
    meson = (ROOT / "meson.build").read_text(encoding="utf-8")
    assert {name for name in re.findall(r"subdir\('(\w+)'\)", meson)} <= listed


def test_the_nautilus_extension_is_installed_only_when_the_option_is_on():
    meson = (ROOT / "src" / "meson.build").read_text(encoding="utf-8")

    assert meson.index("if get_option('nautilus_extension')") < meson.index("nautilus/delta_extension.py")
