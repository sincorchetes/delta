- **The daemon says in its log which repository it works on, and for which one the keyring has no passphrase.** «The passphrase for this
  repository is not in the keyring» said nothing about which, so it could not be told from the log whether the passphrase was missing or
  the daemon was looking for another repository's. Each time the services are built, the repository is logged.
