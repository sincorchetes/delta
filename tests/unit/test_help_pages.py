"""The manual (Mallard pages): well formed, the same in both languages, and quoting the interface exactly."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from test_translations_complete import read_po

ROOT = Path(__file__).resolve().parents[2]
HELP = ROOT / "help"
MALLARD = "{http://projectmallard.org/1.0/}"
LANGUAGES = ("C", "es")
PAGES = sorted(p.name for p in (HELP / "C").glob("*.page"))
SPANISH = read_po(ROOT / "po" / "es.po")


def parse(language: str, name: str) -> ET.Element:
    return ET.parse(HELP / language / name).getroot()


def ids_of(page: ET.Element) -> set[str]:
    return {element.get("id") for element in page.iter() if element.get("id")}


def interface_texts(language: str) -> set[str]:
    """What the application shows: the English msgids, or their Spanish translations."""
    if language == "C":
        return set(SPANISH)
    return {text for entry in SPANISH.values() for text in entry["forms"].values()}


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("name", PAGES)
def test_each_page_is_a_mallard_page_named_by_its_id(language, name):
    page = parse(language, name)

    assert page.tag == f"{MALLARD}page" and page.get("id") == name.removesuffix(".page")
    assert page.get("type") in ("guide", "topic")


def test_both_languages_have_the_same_pages():
    assert sorted(p.name for p in (HELP / "es").glob("*.page")) == PAGES


def test_every_topic_is_linked_from_the_guide_sections_that_exist():
    index = ids_of(parse("C", "index.page"))
    for name in PAGES:
        for link in parse("C", name).iter(f"{MALLARD}link"):
            if link.get("type") == "guide":
                target, _hash, section = link.get("xref").partition("#")
                assert target == "index" and section in index, f"{name}: {link.get('xref')}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_cross_reference_points_to_a_page_and_section_that_exist(language):
    known = {name: ids_of(parse(language, name)) for name in PAGES}
    for name in PAGES:
        for link in parse(language, name).iter(f"{MALLARD}link"):
            target, _hash, section = link.get("xref").partition("#")
            assert target + ".page" in known and (not section or section in known[target + ".page"]), (
                f"{language}/{name}: {link.get('xref')}"
            )


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_button_menu_and_label_the_help_names_is_in_the_application(language):
    texts = interface_texts(language)
    missing = []
    for name in PAGES:
        for gui in parse(language, name).iter(f"{MALLARD}gui"):
            label = re.sub(r"\s+", " ", "".join(gui.itertext())).strip()
            if label not in texts:
                missing.append(f"{language}/{name}: {label!r}")

    assert missing == []


def test_meson_installs_every_language_that_has_pages():
    installed = re.search(r"foreach language : \[([^\]]+)\]", (HELP / "meson.build").read_text(encoding="utf-8"))
    languages = re.findall(r"'([^']+)'", installed.group(1))

    assert sorted(languages) == sorted(p.name for p in HELP.iterdir() if p.is_dir()) == sorted(LANGUAGES)
