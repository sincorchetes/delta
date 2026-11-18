import pytest

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
except (ValueError, ImportError):
    pytest.skip("GTK 4 is not available", allow_module_level=True)

from delta.ui.shortcuts import TRIGGERS


@pytest.mark.parametrize("name", sorted(TRIGGERS))
def test_every_shortcut_is_a_key_combination_gtk_understands(name):
    assert Gtk.ShortcutTrigger.parse_string(TRIGGERS[name]) is not None, TRIGGERS[name]


def test_no_two_actions_share_a_key():
    assert len(set(TRIGGERS.values())) == len(TRIGGERS)


def test_the_actions_the_window_binds_are_the_ones_defined():
    assert set(TRIGGERS) == {"search", "back", "older", "newer", "escape"}
