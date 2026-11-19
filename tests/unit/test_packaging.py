"""The packages of each distribution name the same version and the same files as the build."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def first(pattern: str, text: str) -> str:
    found = re.search(pattern, text, re.MULTILINE)
    assert found is not None, pattern
    return found.group(1)


MESON_VERSION = first(r"^\s+version: '([^']+)',", read("meson.build"))


def test_every_package_names_the_version_of_the_build():
    versions = {
        "rpm": first(r"^Version:\s+(\S+)", read("packaging/rpm/delta-backup.spec")),
        "rpm changelog": first(r"^\* .* - (\S+)-\d+$", read("packaging/rpm/delta-backup.spec")),
        "debian": first(r"^delta-backup \(([^-]+)-\d+\)", read("debian/changelog")),
        "arch": first(r"^pkgver=(\S+)", read("packaging/arch/PKGBUILD")),
        "obs dsc": first(r"^Version: ([^-]+)-\d+$", read("packaging/obs/delta-backup.dsc")),
        "obs dsc tarball": first(r"^DEBTRANSFORM-TAR: delta-(\S+)\.tar\.gz$", read("packaging/obs/delta-backup.dsc")),
        "changelog": first(r"^## \[(\d+\.\d+\.\d+)\]", read("CHANGELOG.md")),
    }

    assert versions == dict.fromkeys(versions, MESON_VERSION)


def test_the_service_of_obs_reads_the_release_branch_and_carries_no_version():
    service = read("packaging/obs/_service")

    assert service.count('<param name="revision">release</param>') == 2
    assert "<param name=\"extract\">packaging/rpm/delta-backup.spec</param>" in service
    assert "<param name=\"extract\">packaging/obs/delta-backup.dsc</param>" in service
    assert '<param name="subdir">debian</param>' in service
    assert not re.search(r"\d+\.\d+\.\d+", service)


def test_the_dsc_for_obs_asks_for_the_same_build_dependencies_as_debian_control():
    control = read("debian/control").split("Package:", 1)[0]
    block = first(r"^Build-Depends:\n((?: .+\n)+)", control)
    in_control = {line.strip().rstrip(",") for line in block.splitlines()}
    in_dsc = {part.strip() for part in first(r"^Build-Depends: (.+)$", read("packaging/obs/delta-backup.dsc")).split(",")}

    assert in_dsc == in_control


def test_every_package_has_the_same_name():
    names = {
        "rpm": first(r"^Name:\s+(\S+)", read("packaging/rpm/delta-backup.spec")),
        "debian source": first(r"^Source: (\S+)", read("debian/control")),
        "debian binary": first(r"^Package: (\S+)", read("debian/control")),
        "arch": first(r"^pkgname=(\S+)", read("packaging/arch/PKGBUILD")),
    }

    assert set(names.values()) == {"delta-backup"}


def test_the_spec_lists_what_the_build_installs():
    spec = read("packaging/rpm/delta-backup.spec")
    build = read("src/meson.build") + read("data/meson.build")

    installed = ("delta-ui", "delta-daemon", "delta_extension.py", "delta.timer", "delta-backup.service", ".gschema.xml")
    for entry in installed:
        assert entry in build and entry in spec, entry


def test_the_arch_and_debian_packages_depend_on_what_the_application_loads():
    arch, control = read("packaging/arch/PKGBUILD"), read("debian/control")

    for library in ("gtk4", "libadwaita", "libsecret", "borg", "fuse3"):
        assert library in arch.split("depends=(", 1)[1].split(")", 1)[0], library
    for typelib in ("gir1.2-gtk-4.0", "gir1.2-adw-1", "gir1.2-secret-1", "borgbackup", "fuse3"):
        assert typelib in control, typelib


def test_every_package_recommends_the_gstreamer_plugins_that_the_preview_of_a_video_needs():
    # Without them GTK stops the whole program, not just the preview (the Nix package lists them as dependencies).
    spec, control, arch = read("packaging/rpm/delta-backup.spec"), read("debian/control"), read("packaging/arch/PKGBUILD")
    recommended = control.split("Recommends:", 1)[1].split("Description:", 1)[0]
    optional = arch.split("optdepends=(", 1)[1].split("\n)", 1)[0]  # not at the first ")": 'yelp: the help (F1)' has one

    for kind in ("base", "good"):
        assert f"Recommends:     gstreamer-plugins-{kind}\n" in spec, f"openSUSE {kind}"
        assert f"Recommends:     gstreamer1-plugins-{kind}\n" in spec, f"Fedora {kind}"
        assert f"gstreamer1.0-plugins-{kind}," in recommended, f"Debian {kind}"
        assert f"'gst-plugins-{kind}:" in optional, f"Arch {kind}"


def test_a_package_can_be_built_without_the_program_that_refreshes_the_icon_cache():
    meson = read("meson.build")

    assert "gtk_update_icon_cache: true" not in meson
    assert re.search(r"find_program\('gtk4-update-icon-cache', 'gtk-update-icon-cache', required: false\)", meson)


def test_the_debian_rules_use_the_meson_build_and_the_copyright_names_the_licence_of_the_project():
    assert "--buildsystem=meson" in read("debian/rules")
    assert "License: GPL-3+" in read("debian/copyright")
    assert "GPL-3.0-or-later" in read("meson.build")
