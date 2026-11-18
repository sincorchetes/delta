"""SecretStore adapter over libsecret (gnome-keyring / any Secret Service)."""

import threading
from collections.abc import Callable
from typing import TypeVar

import gi

gi.require_version("Gio", "2.0")
gi.require_version("Secret", "1")
from gi.repository import Gio, GLib, Secret

from delta.domain.errors import SecretStoreError
from delta.i18n import _

SCHEMA = Secret.Schema.new(
    "org.gnome.Delta",  # the name the passphrases were stored under: changing it would lock people out of their backups
    Secret.SchemaFlags.NONE,
    {"repository": Secret.SchemaAttributeType.STRING},
)

# A locked keyring makes libsecret wait for someone to answer an unlock prompt.
# Without a limit that would leave a backup job "running" forever.
DEFAULT_TIMEOUT_SECONDS = 60.0

T = TypeVar("T")


def run_with_timeout(call: Callable[[Gio.Cancellable], T], timeout: float) -> T:
    """Run a cancellable libsecret call, cancelling it after `timeout` seconds."""
    cancellable = Gio.Cancellable()
    timer = threading.Timer(timeout, cancellable.cancel)
    timer.start()
    try:
        return call(cancellable)
    except GLib.Error as err:
        if err.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
            raise SecretStoreError(
                _("Timed out waiting for the keyring. Is it locked?")
            ) from err
        if err.matches(Gio.DBusError.quark(), Gio.DBusError.SERVICE_UNKNOWN):
            raise SecretStoreError(_("The keyring service is not available.")) from err
        raise SecretStoreError(err.message) from err
    finally:
        timer.cancel()


def _attributes(key: str) -> dict[str, str]:
    return {"repository": key}


class LibsecretStore:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    def get(self, key: str) -> str | None:
        return run_with_timeout(
            lambda cancellable: Secret.password_lookup_sync(SCHEMA, _attributes(key), cancellable),
            self._timeout,
        )

    def set(self, key: str, secret: str) -> None:
        label = _("Delta backup passphrase for {repository}").format(repository=key)
        run_with_timeout(
            lambda cancellable: Secret.password_store_sync(
                SCHEMA, _attributes(key), Secret.COLLECTION_DEFAULT, label, secret, cancellable
            ),
            self._timeout,
        )

    def delete(self, key: str) -> None:
        run_with_timeout(
            lambda cancellable: Secret.password_clear_sync(SCHEMA, _attributes(key), cancellable),
            self._timeout,
        )
