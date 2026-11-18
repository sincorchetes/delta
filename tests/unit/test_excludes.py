from delta.daemon.composition import DEFAULT_EXCLUDES, resolve_excludes

HOME = "/home/user"
BUILTIN = tuple(f"{HOME}/{p}" for p in DEFAULT_EXCLUDES)


def test_without_choices_only_the_builtin_exclusions_apply():
    assert resolve_excludes((), HOME) == BUILTIN


def test_chosen_paths_become_literal_prefix_patterns():
    assert resolve_excludes(("/home/user/Downloads",), HOME) == (*BUILTIN, "pp:/home/user/Downloads")


def test_special_characters_stay_literal_and_never_become_wildcards():
    (pattern,) = resolve_excludes(("/data/[1]*?",), HOME)[len(BUILTIN):]
    assert pattern == "pp:/data/[1]*?"  # `pp:` matches the path literally


def test_tilde_is_expanded_paths_are_normalised_and_duplicates_dropped():
    result = resolve_excludes(("~/Videos", "/srv//x/", "/srv/x"), HOME)[len(BUILTIN):]
    assert result[1:] == ("pp:/srv/x",) and result[0].startswith("pp:/") and "~" not in result[0]


def test_relative_entries_are_ignored_not_guessed():
    assert resolve_excludes(("Downloads", "../etc"), HOME) == BUILTIN
