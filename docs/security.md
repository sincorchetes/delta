# Delta security

The threat model and the guarantees **that the code meets today**. What does not exist yet is in "Known limits"; it is not
taken as covered.

## What is protected, and from whom

- **The user's data** in the backups: encrypted by Borg (`repokey-blake2`, even locally), with deduplication and integrity.
- **The repository key** (the passphrase): without it there is no readable backup.
- **The original files** against our own operations: restoring must never destroy what the user has.

Threats considered: a compromised or lost backup disk, a mistake by the user (restoring on top of something, unlocking at the
wrong time) and a failure of ours when handing data to Borg. **Out of scope**: malicious software running as the user
itself (see the limits).

## Secrets

- The passphrase lives in **libsecret** (the desktop keyring). Never in GSettings, configuration files, argv or environment
  variables.
- It reaches Borg through a **pipe on fd 3** (`BORG_PASSPHRASE_FD`), only to the child process. If the keyring does not have it,
  the operation fails with a clear error instead of letting Borg ask on a terminal that does not exist.
- The wizard generates a **recovery key** (30 characters without ambiguous ones) and does not let you finish without saving it to
  a file or explicitly accepting the risk. "Copy" does not count as saved. The file is created with private permissions
  (`G_FILE_CREATE_PRIVATE`, 0600).
- `borg key export` **is not enough** without the passphrase: the recovery key is the only thing that allows reading the backups
  if the keyring is lost.

## External processes

- Always `Gio.Subprocess` with an argument list (argv). Never `shell=True` or shell strings. The user's paths travel as one more
  argument, never interpolated.
- Borg's commands are built in pure functions (`infrastructure/borg_commands.py`) and tested without running them.

## Paths and restoring

- The D-Bus API validates paths before calling Borg: absolute, without `..`, and when restoring **inside the home folder after
  resolving symlinks** (`domain/paths.py`, `RestoreService.prepare`).
- Restoring **does not overwrite** by default: `RestoreAsCopy` leaves the old version next to the original with another name.
  `RestoreReplace` first sets the current version aside (`… (before restoring …)`) and, if it fails, puts it back in its place.
- Invalid backup sources are discarded; if the user configured folders and none is valid, the backup **fails** instead of
  widening to all of `$HOME`.

## Destinations

- Delta stores backups **only on this computer** (a folder or a connected drive). `Repository` requires a local absolute path,
  so Borg never opens a connection: there are no host keys or credentials to manage. An invalid location inherited in the
  configuration is treated as "not configured".

## Repository locks

- `borg break-lock` **is never run by itself**. Only on an explicit request from the user, after a dialog that warns that
  unlocking a repository in use can damage it. The daemon admits only one job at a time, so it does not unlock under a backup of
  its own that is running.

## System permissions

- The daemon runs in the **user session**, with no extra privileges or polkit.
- The parent directories of a local repository are created with 0700.
- Scheduling is a `systemd --user` timer; Delta installs nothing at the system level.

## Data that appears in notifications and logs

- Notifications show Borg's error message, cut to 300 characters; it can contain the user's paths. It is a usability decision: they
  can be seen in the notification center.
- Delta does not write passphrases to the daemon's log (the user journal).

## Known limits

- **Software of the same user**: any process that runs as the user can read the unlocked keyring, the session bus and the files.
  Delta does not try to isolate itself from that.
- **The passphrase goes through the session bus** once, from the app to the daemon, when the wizard generates the recovery key
  (the session bus is private to the user, but it is not an isolated channel).
- **Flatpak**: to back up and restore it needs access to the home folder and to `/run/media` (`--filesystem=home`,
  `--filesystem=/run/media`), which is broad. It never mounts backups. The native package is the primary distribution.
- **Browsing a backup as a folder** (native install only): while a backup is mounted, anything running as the user can read it,
  and it blocks the backups (the repository has a single lock). That is why the daemon interrupts or postpones the backup, closes
  the folder when it is no longer used, when the session is locked or suspended, and detaches it with `fusermount3 -u -z` so
  that no mount is left hanging.
- There is **no external audit**.
