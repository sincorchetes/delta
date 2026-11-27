"""What the daemon says about which repository it works on, so that a missing passphrase can be told from the log."""

import logging

from delta.daemon import composition
from delta.domain.repository import Repository
from delta.domain.retention import RetentionPolicy
from delta.infrastructure.borg_runner import BorgRunner


def configure(monkeypatch, repository):
    monkeypatch.setattr(composition, "configured_repository", lambda: repository)
    monkeypatch.setattr(composition, "configured_sources", lambda: ())
    monkeypatch.setattr(composition, "configured_excludes", lambda: ())
    monkeypatch.setattr(composition, "configured_retention", lambda: RetentionPolicy())


def said(caplog, name):
    return [(r.levelname, r.getMessage()) for r in caplog.records if r.name == name]


def test_every_build_of_the_services_says_which_repository_they_are_for(monkeypatch, caplog):
    configure(monkeypatch, Repository("/media/disk/bck"))
    caplog.set_level(logging.INFO)

    composition.build_services(object())

    assert said(caplog, "delta.daemon.composition") == [("INFO", "the services are built for the repository at /media/disk/bck")]


def test_building_them_with_nothing_configured_says_so(monkeypatch, caplog):
    configure(monkeypatch, None)
    caplog.set_level(logging.INFO)

    composition.build_services(object())

    assert said(caplog, "delta.daemon.composition") == [("INFO", "the services are built for the repository at (none)")]


def test_a_keyring_without_the_passphrase_says_for_which_repository(tmp_path, caplog):
    class EmptyKeyring:
        def get(self, key):
            return None

    runner = BorgRunner(env={"BORG_BASE_DIR": str(tmp_path)}, secrets=EmptyKeyring())

    try:
        runner._pass_passphrase(None, Repository("/media/disk/bck"))
    except Exception:  # the error itself is tested with the others of its kind
        pass

    assert said(caplog, "delta.infrastructure.borg_runner") == [
        ("WARNING", "the keyring has no passphrase for the repository at /media/disk/bck")
    ]
