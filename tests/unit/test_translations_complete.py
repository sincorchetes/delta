"""Every text the user can see is translated: nothing is left in English, and no file is forgotten.

Reads the sources and `po/es.po` directly, so it needs no gettext tools.
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "src"
PO = ROOT / "po"
GETTEXT_CALLS = {"_", "ngettext"}
PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")


def listed_files() -> list[Path]:
    lines = (PO / "POTFILES.in").read_text(encoding="utf-8").splitlines()
    return [ROOT / line for line in lines if line.endswith(".py")]


def strings_in(path: Path) -> list[tuple[str, str | None]]:
    """(msgid, msgid_plural) for each call of `_()` or `ngettext()` in a source file."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in GETTEXT_CALLS):
            continue
        texts = [arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
        if node.func.id == "_" and texts:
            found.append((texts[0], None))
        elif node.func.id == "ngettext" and len(texts) >= 2:
            found.append((texts[0], texts[1]))
    return found


def unquote(text: str) -> str:
    return ast.literal_eval(text)


def read_po(path: Path) -> dict[str, dict]:
    """msgid -> {"plural", "forms", "fuzzy"}; the header (empty msgid) is left out."""
    entries, current, target, fuzzy = {}, None, None, False
    for raw in path.read_text(encoding="utf-8").splitlines() + [""]:
        line = raw.strip()
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith("msgid_plural"):
            current["plural"], target = unquote(line[len("msgid_plural"):].strip()), ("plural",)
        elif line.startswith("msgid"):
            current = {"id": unquote(line[5:].strip()), "plural": None, "forms": {}, "fuzzy": fuzzy}
            target = ("id",)
        elif line.startswith("msgstr["):
            index, _sep, rest = line[7:].partition("]")
            current["forms"][int(index)] = unquote(rest.strip())
            target = ("forms", int(index))
        elif line.startswith("msgstr"):
            current["forms"][0] = unquote(line[6:].strip())
            target = ("forms", 0)
        elif line.startswith('"') and current is not None:
            piece = unquote(line)
            if target[0] == "forms":
                current["forms"][target[1]] += piece
            else:
                current[target[0]] += piece
        elif not line:
            if current is not None and current["id"]:
                entries[current["id"]] = current
            current, fuzzy = None, False
    return entries


SPANISH = read_po(PO / "es.po")
USED = [(path, msgid, plural) for path in listed_files() for msgid, plural in strings_in(path)]


def test_the_list_of_files_to_translate_names_files_that_exist():
    assert all(path.exists() for path in listed_files())


def test_every_file_that_marks_texts_for_translation_is_in_the_list():
    listed = set(listed_files())
    marking = {
        path
        for path in SOURCES.rglob("*.py")
        if "i18n" not in path.name and strings_in(path)
    }

    assert sorted(p.relative_to(ROOT).as_posix() for p in marking - listed) == []


VISIBLE = {"label", "title", "subtitle", "tooltip_text", "description", "body", "placeholder_text"}
NOT_WORDS = re.compile(r"^[^A-Za-z]*$")


SETTERS = {"set_title", "set_label", "set_subtitle", "set_description", "set_tooltip_text", "set_body"}
TEXT_CONSTRUCTORS = {("Label", "new"), ("Toast", "new"), ("AlertDialog", "new")}


def untranslated_visible_texts(path: Path) -> list[str]:
    """Plain string literals given where the user will read them, never passed through `_()`."""
    found = []

    def literal(value, where):
        if isinstance(value, ast.Constant) and isinstance(value.value, str) and not NOT_WORDS.match(value.value):
            found.append(f"{path.name}:{value.lineno} {where}={value.value!r}")

    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg in VISIBLE:
                literal(keyword.value, keyword.arg)
        function = node.func
        if not isinstance(function, ast.Attribute):
            continue
        if function.attr in SETTERS and node.args:
            literal(node.args[0], function.attr)
        elif function.attr == "add_response" and len(node.args) > 1:
            literal(node.args[1], "add_response")
        elif isinstance(function.value, ast.Attribute) and (function.value.attr, function.attr) in TEXT_CONSTRUCTORS:
            for argument in node.args:
                literal(argument, f"{function.value.attr}.{function.attr}")
    return found


def test_the_check_for_left_out_texts_sees_what_it_should(tmp_path):
    source = tmp_path / "window.py"
    source.write_text(
        "Gtk.Button(label='Open', icon_name='folder-symbolic')\n"
        "Gtk.Button(label=_('Open'))\n"
        "row.set_title('Plain')\n"
        "dialog.add_response('cancel', 'Cancel')\n"
        "Adw.Toast.new('Done')\n"
        "Gtk.Label.new('—')\n"
        "Gtk.Label(label='')\n",
        encoding="utf-8",
    )

    assert untranslated_visible_texts(source) == [
        "window.py:1 label='Open'",
        "window.py:3 set_title='Plain'",
        "window.py:4 add_response='Cancel'",
        "window.py:5 Toast.new='Done'",
    ]


def test_no_visible_text_is_left_out_of_translation():
    leftovers = [text for path in (SOURCES / "delta" / "ui").glob("*.py") for text in untranslated_visible_texts(path)]

    assert leftovers == []


@pytest.mark.parametrize(("path", "msgid", "plural"), USED, ids=[f"{p.name}:{m[:40]}" for p, m, _ in USED])
def test_each_text_has_a_complete_spanish_translation(path, msgid, plural):
    entry = SPANISH.get(msgid)

    assert entry is not None, f"{path.name}: missing in po/es.po"
    assert not entry["fuzzy"], f"{path.name}: marked fuzzy"
    forms = entry["forms"]
    expected = 2 if plural else 1
    assert sorted(forms) == list(range(expected)) and all(forms.values()), f"{path.name}: not translated"
    for form in forms.values():
        assert set(PLACEHOLDER.findall(form)) == set(PLACEHOLDER.findall(msgid)), f"{path.name}: placeholders differ"
