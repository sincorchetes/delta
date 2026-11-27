- **When the keyring no longer has the passphrase of your backups, the window asks for it.** Instead of «The last backup failed» with a
  «Try again» that could not help, it says that the passphrase is not in the keyring and offers **«Enter passphrase…»**: the daemon
  opens the repository with what you type and keeps it in the keyring only if it opens. Before, the only way was *Preferences →
  Destination → Change…* choosing the same folder again.
