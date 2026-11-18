"""The website's sources: both languages have the same pages, each one described, listed and illustrated."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "website" / "src" / "content" / "docs"
SHOTS = ROOT / "website" / "src" / "assets" / "screenshots"
FOLDERS = {"en": DOCS, "es": DOCS / "es"}
THEMES = ("light", "dark")


def pages(language: str) -> dict[str, str]:
    return {page.stem: page.read_text(encoding="utf-8") for page in FOLDERS[language].glob("*.mdx")}


def shots(text: str) -> list[str]:
    return re.findall(r'<Shot\s+name="([^"]+)"', text)


def test_both_languages_have_the_same_pages():
    assert pages("en").keys() == pages("es").keys()


def test_every_page_has_a_title_and_a_description():
    for language in FOLDERS:
        for name, text in pages(language).items():
            front = text.split("---")[1]
            assert re.search(r"^title: \S", front, re.MULTILINE), f"{language}/{name}: no title"
            assert re.search(r"^description: \S", front, re.MULTILINE), f"{language}/{name}: no description"


def test_the_sidebar_lists_every_page_but_the_home_and_nothing_that_does_not_exist():
    config = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    listed = [slug for group in re.findall(r"items: \[([^\]]*)\]", config) for slug in re.findall(r"'([a-z-]+)'", group)]

    assert sorted(listed) == sorted(set(pages("en")) - {"index"})


def test_every_screenshot_has_alt_text_and_exists_in_both_languages_and_themes():
    for language in FOLDERS:
        for name, text in pages(language).items():
            assert len(re.findall(r'<Shot\s+[^>]*alt="[^"]+"', text)) == len(shots(text)), f"{language}/{name}: alt"
            for shot in shots(text):
                for lang in FOLDERS:
                    for theme in THEMES:
                        assert (SHOTS / f"{shot}-{lang}-{theme}.png").is_file(), f"{shot}-{lang}-{theme}.png"


def test_a_page_shows_the_same_screenshots_in_both_languages():
    english, spanish = pages("en"), pages("es")

    for name in english:
        assert shots(english[name]) == shots(spanish[name]), name


def test_the_site_ships_the_file_that_names_its_domain():
    assert (ROOT / "website" / "public" / "CNAME").read_text(encoding="utf-8").strip() != ""
