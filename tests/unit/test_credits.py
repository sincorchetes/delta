"""Who is credited, the version, and the license, kept the same everywhere they are written."""

import re
from pathlib import Path

import delta
from delta.ui import credits

ROOT = Path(__file__).resolve().parents[2]


def test_the_author_and_the_co_author_are_credited():
    assert credits.AUTHOR == "Álvaro Castillo" and credits.WEBSITE == "https://sincorchetes.tech"
    assert credits.CO_AUTHOR == "Claude (Anthropic)" and credits.CO_AUTHOR_URL == "https://claude.ai"


def test_the_repository_and_the_documentation_are_where_the_project_says():
    assert credits.REPOSITORY == "https://github.com/sincorchetes/delta"
    assert credits.DOCUMENTATION == "https://delta.sincorchetes.tech"


def test_the_version_is_the_same_in_the_package_meson_and_pyproject():
    meson = re.search(r"version:\s*'([^']+)'", (ROOT / "meson.build").read_text(encoding="utf-8")).group(1)
    pyproject = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)

    assert delta.__version__ == meson == pyproject


def test_the_license_is_the_same_in_meson_and_in_the_dialog():
    meson = re.search(r"license:\s*'([^']+)'", (ROOT / "meson.build").read_text(encoding="utf-8")).group(1)

    assert credits.LICENSE == meson == "GPL-3.0-or-later"


def test_the_license_text_is_in_the_repository():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")

    assert "GNU GENERAL PUBLIC LICENSE" in text and "Version 3, 29 June 2007" in text


def test_every_component_has_a_name_a_license_and_a_link():
    assert credits.RUNTIME and all(c.name and c.license and c.url.startswith("https://") for c in credits.RUNTIME)


def test_every_runtime_component_is_in_the_third_party_list():
    listed = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")

    assert [c.name for c in credits.RUNTIME if c.name not in listed] == []
