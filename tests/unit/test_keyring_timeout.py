import time

import gi
import pytest

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from delta.domain.errors import SecretStoreError

try:
    from delta.infrastructure.libsecret_store import run_with_timeout
except ValueError:
    pytest.skip("libsecret typelib not available", allow_module_level=True)


def _blocks_until_cancelled(cancellable):
    """Stands in for libsecret waiting on an unlock prompt nobody answers."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if cancellable.is_cancelled():
            raise GLib.Error.new_literal(
                Gio.io_error_quark(), "Operation was cancelled", Gio.IOErrorEnum.CANCELLED
            )
        time.sleep(0.01)
    raise AssertionError("never cancelled")


def test_a_call_stuck_on_a_locked_keyring_times_out_with_a_clear_error():
    started = time.monotonic()

    with pytest.raises(SecretStoreError, match="keyring"):
        run_with_timeout(_blocks_until_cancelled, timeout=0.2)

    assert time.monotonic() - started < 2


def test_a_fast_call_returns_its_value_without_waiting():
    started = time.monotonic()

    assert run_with_timeout(lambda cancellable: "secret", timeout=30) == "secret"

    assert time.monotonic() - started < 1


def test_a_keyring_service_that_is_not_running_gets_a_readable_message():
    def absent(cancellable):
        raise GLib.Error.new_literal(
            Gio.DBusError.quark(), "The name is not activatable", Gio.DBusError.SERVICE_UNKNOWN
        )

    with pytest.raises(SecretStoreError, match="keyring service is not available"):
        run_with_timeout(absent, timeout=30)


def test_other_keyring_errors_keep_their_message():
    def refuses(cancellable):
        raise GLib.Error.new_literal(Gio.io_error_quark(), "service unavailable", Gio.IOErrorEnum.FAILED)

    with pytest.raises(SecretStoreError, match="service unavailable"):
        run_with_timeout(refuses, timeout=30)
