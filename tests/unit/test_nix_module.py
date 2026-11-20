"""The Home Manager module links, into XDG_DATA_HOME, what the desktop looks for there; the NixOS one declares it for the system."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = (ROOT / "nix" / "home-manager.nix").read_text(encoding="utf-8")
NIXOS = (ROOT / "nix" / "nixos.nix").read_text(encoding="utf-8")


def field(pattern: str, text: str) -> str:
    found = re.search(pattern, text)
    assert found is not None, pattern
    return found.group(1)


def unit(name: str) -> dict[str, str]:
    """The `Key=value` lines of a systemd unit of the package (the last of a repeated key wins)."""
    text = (ROOT / "data" / "systemd" / name).read_text(encoding="utf-8")
    return dict(line.split("=", 1) for line in text.splitlines() if re.match(r"^[A-Za-z]+=", line))


def test_the_manual_is_linked_where_yelp_looks_for_it():
    block = re.search(r'"help" = \{\s*source = "\$\{share\}/help";\s*recursive = true;\s*\};', MODULE)

    assert block is not None


def test_what_a_session_needs_to_find_without_the_nix_profile_in_its_data_dirs_is_linked():
    for target in ("systemd/user", "dbus-1/services", "locale", "glib-2.0/schemas", "help"):
        assert f'"{target}" = {{' in MODULE, target
    for entry in ("Delta", "Delta.Daemon", "Delta.Versions"):
        assert f'"applications/io.github.sincorchetes.{entry}.desktop"' in MODULE, entry


def test_the_nixos_module_takes_no_flake_so_that_configuration_nix_can_import_it():
    assert NIXOS.lstrip().startswith("{ config, lib, pkgs, ... }:")
    assert not re.search(r"\bself\b", NIXOS)
    assert 'default = pkgs.callPackage ./package.nix { };' in NIXOS


def test_the_flake_offers_the_two_modules():
    flake = (ROOT / "flake.nix").read_text(encoding="utf-8")

    assert "homeManagerModules.default = import ./nix/home-manager.nix self;" in flake
    assert "nixosModules.default = ./nix/nixos.nix;" in flake


def test_the_units_of_the_nixos_module_are_the_ones_of_data_systemd():
    # NixOS builds /etc/systemd/user only from its options, so the units are written again in the module: this keeps them equal.
    timer, daemon, trigger = unit("delta.timer"), unit("delta.service.in"), unit("delta-backup.service.in")
    exec_start = trigger["ExecStart"]

    assert f'OnCalendar = "{timer["OnCalendar"]}";' in NIXOS
    assert f'Unit = "{timer["Unit"]}";' in NIXOS and "Persistent = true;" in NIXOS and timer["Persistent"] == "true"
    assert f'Type = "{daemon["Type"]}";' in NIXOS and f'bus = "{daemon["BusName"]}";' in NIXOS
    assert f'Type = "{trigger["Type"]}";' in NIXOS
    object_path, method, dest = (field(rf"--{name} (\S+)", exec_start) for name in ("object-path", "method", "dest"))
    assert f'"--object-path {object_path}"' in NIXOS
    assert f'"--method ${{bus}}.{method.rsplit(".", 1)[1]}"' in NIXOS
    assert dest == daemon["BusName"] and method.startswith(f"{dest}.")


def test_what_a_session_finds_through_the_system_profile_is_in_the_nixos_module():
    for path in ("/share/nautilus-python/extensions", "/share/help", "/share/locale"):
        assert f'"{path}"' in NIXOS, path
    assert "services.dbus.packages = [ cfg.package ];" in NIXOS
    assert "pkgs.nautilus-python" in NIXOS
    assert "gsettings-schemas/${cfg.package.name}" in NIXOS


def test_the_nix_package_uses_the_python_of_the_nixpkgs_it_is_built_with_and_not_the_pins_of_the_lock():
    # Like every other distribution: its channel's interpreter and its PyGObject, with no version or hash of ours.
    python = (ROOT / "nix" / "python.nix").read_text(encoding="utf-8")

    assert "pygobject3" in python
    for pinned in ("fetchurl", "overridePythonAttrs", "packageOverrides", "pythonhosted", "sha256", "python313"):
        assert pinned not in python.replace("The pins of uv.lock", ""), pinned
