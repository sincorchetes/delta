"""The AppStream metadata, the desktop entry and the icons say the same as the code, and point to files that exist."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import delta
from delta.ui import credits

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
APP_ID = "io.github.sincorchetes.Delta"
METAINFO = ET.parse(DATA / f"{APP_ID}.metainfo.xml.in").getroot()


def text_of(tag: str) -> str:
    return METAINFO.findtext(tag) or ""


def test_the_component_is_the_application_and_its_desktop_entry():
    assert METAINFO.get("type") == "desktop-application" and text_of("id") == APP_ID
    assert text_of("launchable") == f"{APP_ID}.desktop" and (DATA / f"{APP_ID}.desktop.in").exists()


def test_the_licenses_are_the_projects_and_a_free_one_for_the_metadata():
    assert text_of("project_license") == credits.LICENSE and text_of("metadata_license") == "CC0-1.0"


def test_the_categories_are_declared_and_are_the_ones_of_the_desktop_entry():
    declared = {category.text for category in METAINFO.iter("category")}
    entry = (DATA / f"{APP_ID}.desktop.in").read_text(encoding="utf-8")
    in_entry = set(re.search(r"^Categories=(.*)$", entry, re.M).group(1).strip(";").split(";"))

    assert declared and declared <= in_entry


def test_the_summary_is_short_enough_for_a_software_centre():
    assert 0 < len(text_of("summary")) <= 35


def test_the_links_are_the_documentation_and_the_repository():
    urls = {url.get("type"): url.text for url in METAINFO.iter("url")}

    assert urls["homepage"] == urls["help"] == credits.DOCUMENTATION
    assert urls["vcs-browser"] == credits.REPOSITORY and urls["bugtracker"] == f"{credits.REPOSITORY}/issues"


def test_the_current_version_has_a_release_entry():
    assert delta.__version__ in [release.get("version") for release in METAINFO.iter("release")]


def test_every_screenshot_is_a_file_of_the_repository():
    images = [image.text for image in METAINFO.iter("image")]

    assert images and all(
        (ROOT / re.sub(r"^https://raw\.githubusercontent\.com/sincorchetes/delta/main/", "", url)).is_file() for url in images
    )
    assert len([s for s in METAINFO.iter("screenshot") if s.get("type") == "default"]) == 1


def test_every_screenshot_has_a_caption_for_those_who_cannot_see_it():
    assert all(screenshot.findtext("caption") for screenshot in METAINFO.iter("screenshot"))


def test_the_desktop_entries_use_the_application_icon():
    for entry in DATA.glob("*.desktop.in"):
        assert f"\nIcon={APP_ID}\n" in entry.read_text(encoding="utf-8"), entry.name


def test_the_icons_are_valid_svg_at_the_sizes_gnome_expects():
    full = ET.parse(DATA / "icons/hicolor/scalable/apps" / f"{APP_ID}.svg").getroot()
    symbolic = ET.parse(DATA / "icons/hicolor/symbolic/apps" / f"{APP_ID}-symbolic.svg").getroot()

    assert full.tag == symbolic.tag == "{http://www.w3.org/2000/svg}svg"
    assert full.get("viewBox") == "0 0 128 128" and symbolic.get("viewBox") == "0 0 16 16"


def test_meson_installs_the_icons_the_metadata_and_the_translated_entry():
    meson = (DATA / "meson.build").read_text(encoding="utf-8")

    for name in (f"{APP_ID}.svg", f"{APP_ID}-symbolic.svg", f"{APP_ID}.metainfo.xml.in", f"{APP_ID}.desktop"):
        assert name in meson, name


def test_the_texts_users_read_in_the_store_are_in_the_translation_list():
    listed = (ROOT / "po" / "POTFILES.in").read_text(encoding="utf-8").splitlines()

    assert f"data/{APP_ID}.metainfo.xml.in" in listed and f"data/{APP_ID}.desktop.in" in listed
