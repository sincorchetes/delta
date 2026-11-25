# Changelog

All notable changes to Delta are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- **The check of a published package on Fedora no longer waits for a version it already has.** `dnf install` of a package that is
  installed does nothing in DNF 5, so after the first try it never took the newer version that the Build Service published, and the
  job failed after 180 minutes although the package was there (a fault of the check, not of the package).

- **The icon of a check in progress is a clean symbolic one**, like those of the other states (the previous one was drawn as a blurry
  bitmap), and the daemon says in its log when a check starts and how it ended.

## [0.4.0] - 2026-11-25

### Added

- **The daemon can check that your backups can be read.** `CheckRepository` runs `borg check --repository-only` (whether the files
  of the repository are readable; the check of every backup's data takes far longer and is not made), as a job of its own kind:
  `Status` is `checking` while it runs, `CancelCheck` stops it, and it never runs under a backup. A repository with problems is
  told as such, with what Borg said, and a drive that is gone says why instead.
- **«Check backups» in the main menu of the window.** It starts that check; while it runs the window says so and offers to cancel
  it, and it ends with a sentence in a toast or, when it found problems, a dialog where they can be read.

### Fixed

- **The text for a read-only place says that the drive may be failing.** A drive with errors can refuse writes while it is still
  mounted for writing (ext4 does it when its journal fails), so «mount it again» was not enough: the text now adds that, if this
  came after an error, the drive may be failing.

## [0.3.0] - 2026-11-24

### Changed

- **The window learns that the drive is gone without waiting for a backup.** The daemon looks at the place of the backups in the
  background (every ten seconds, and whenever a drive is mounted or taken away) and answers `Status` and `UnavailableReason` with
  what it finds, so pulling the drive shows «not connected» in a few seconds. A drive that hangs holds up a thread, not the daemon.

### Fixed

- **A drive that goes read-only in the middle of a backup is told as such.** When Borg stopped with an internal error, only its
  one-line account was looked at, which does not name the folder, so the window said «The last backup failed». The whole report
  is now kept with the error and the cause is read from it: a read-only place is the destination's if the report names its folder.

- **The folder chooser of the wizard opens where you were.** Typing a folder that does not exist yet and pressing «Choose…» left
  you among the recent files; it now opens in the nearest folder that exists on the way, and the page says that a folder that
  does not exist is created.

- **The history says why it is short.** A line under the count tells that old backups are removed to save space and that how
  many are kept is a preference.

- **«Unlock…» on a drive that is gone says so.** The window can still show an old «locked» error after the drive was pulled; asking
  to unlock now checks the place first and tells why it cannot be used, instead of Borg's own words.

- **A backup that waits for its drive is not logged as a warning.** «The drive is not connected» and the other causes of an
  unusable destination are an expected state, so the daemon logs them as information; only real failures are warnings.

- **A drive that fails while it is written to is told as such.** The engine's failures are now told by the number of the system's
  error that it reports, not by its words: an input/output error (a drive pulled or failing) is its own cause, «The drive with
  your backups reports errors», with its notification; «could not create the lock» for a read-only or forbidden place is no
  longer shown as a locked repository with «Unlock…»; and a crash of Borg is told in one line («Borg stopped unexpectedly: …»)
  instead of its whole traceback, which goes to the log.
- **A destination that is too full for Borg to go on is told as full**, not as «The last backup failed» with Borg's English: Borg
  refuses to commit when what is free is less than what it needs («Insufficient free space to complete transaction»), even if the
  disk still has room. Found with a small drive: the window said «The place with your backups is full» when the disk was at
  100 %, and Borg's own text when it was a little below.

## [0.2.0] - 2026-11-20

### Added

- **Another repository in the place of yours is noticed.** Delta remembers the identifier of the repository it made or adopted
  (in the setting `repository-id`, learnt at the first backup for those who already had one) and, before a backup, compares it
  with the one it finds: if it is another, even with the same passphrase, nothing is written in it and the window says «These
  are not your backups». To accept it, choose that folder again in *Preferences → Destination → Change…* and give its passphrase.

## [0.1.3] - 2026-11-20

### Added

- **Change where backups are kept**, from Preferences → Destination → *Change…*. What is backed up and how long it is kept
  stay as they are, and the backups already made are left where they were: the password of each repository stays in your
  keyring, so going back to it needs nothing.

### Changed

- **A drive that is connected but is not the one with your backups says so**, instead of «not connected»: another disk (or a
  wiped one) in the same place gets «Your backups are not on this drive». The root of a freshly formatted drive (which holds only
  the `lost+found` that the file system makes) is a folder you can use in the wizard, not «not empty».
- **A place that cannot be written to is not a failed backup either: full, read-only, no permission.** Each cause has its own
  name, window text, notification (told once, and again after a week) and hint, in your language and not with Borg's list of
  files. A full destination used to show «The last backup failed» with a line for every file and `[Errno 28]`. The wizard also
  refuses a read-only place, or one you have no permission to write in, when you choose it.

- **A folder that already holds your backups is reopened, not refused.** If you set Delta up again (the settings were
  deleted, a new computer) and choose the folder of an existing repository, the wizard asks for its passphrase and keeps
  using it instead of saying «That folder is not empty». It also says when the place is on a drive that is not connected,
  rather than creating the folders on the disk of the computer.

- **A drive with your backups that is not connected is no longer a failed backup.** It has its own state, error and messages:
  the window says «The drive with your backups is not connected» and where it has to be, in your language and not with Borg's
  text, and nothing is started or announced for a drive that is not there. The place counts as unreachable when its folder is not
  there or is empty (the mount point of a drive that is not mounted). A folder that is there but holds no repository is still a
  different error. You are told once, not at every hourly try, and reminded after a week; a good
  backup starts the count again. When you connect the drive, the backup that was waiting for it is made at once.

### Fixed

- **The daemon did not start on Fedora 43, Debian 13, Rocky Linux 10 and AlmaLinux 10** (version 0.1.2), so Delta did nothing
  there: it called `GLibUnix.signal_add`, which only the newest GLib has (`AttributeError` at startup). It now watches the stop
  signals with a source, which every GLib that has `GLibUnix` supports. The tests never saw it because the one for the startup
  replaced GLib with a stand-in; now one uses the real GLib.

- **A system without GStreamer no longer closes Delta when a video or audio is previewed.** The preview plays through
  GStreamer, and when it cannot find what it needs (the plugins, a GL library) GTK ends the whole program, which cannot be
  caught. Delta now tries to make the player in a process of its own, once, and where that fails it offers the file to its own
  application, as it does for a file it cannot play.
- **The packages recommend the GStreamer plugins** that the preview needs: the RPM, the `.deb` and the Arch package (the Nix
  package already included them).
- **The Nix package uses the Python libraries of its own nixpkgs**, not the versions of `uv.lock`, as the other distributions use
  what their packaging ships. It is built and checked, with its NixOS module, on `nixos-unstable` and on `nixos-26.05`.

## [0.1.2] - 2026-11-19

### Added

- **A NixOS module** (`nixosModules.default`) for `configuration.nix`, with or without flakes: `services.delta.enable = true;`
  installs Delta and sets up its user service and timer, the D-Bus service, the settings and the menu of Files.

### Fixed

- **A backup folder inside what you back up** (for example `~/Backups` with your home folder as the source) is no longer copied
  into itself: the repository is always skipped.

### Changed

- **A release is published by pushing its tag.** The GitHub Release (with the notes of this file) and the Flatpak bundle, the
  AUR package (with the real checksum) and the openSUSE Build Service repositories are made from the tag, with nothing uploaded
  by hand.

## [0.1.1] - 2026-11-18

No change to the program: packaging and documentation.

### Added

- **A Flatpak bundle** attached to each release, built by CI offline from pinned sources (GNOME 51 runtime).
- **Repositories** for Fedora, Rocky Linux, AlmaLinux, openSUSE, Debian and Ubuntu (openSUSE Build Service) and a package in the AUR,
  with the installation page rewritten around them.

### Fixed

- The optional dependency of the Arch package is `nautilus-python`, the real name of the package.

## [0.1.0] - 2026-11-18

The first release.

### Added

- **Time travel for your files.** *Restore Previous Version…* in Files for any file or folder, and a *Previous versions* window
  with a timeline of every copy, a preview (image, text, video and audio) and a folder browser that compares each entry with
  the disk, filters by what changed, searches by name and recovers what was deleted.
- **Restore** as a copy next to the original, or replacing the current version (which is set aside first and put back if
  anything fails).
- **Browse a backup as a folder** with `borg mount` (native install only), with the backup paused while it is open.
- **BorgBackup as the engine:** incremental, deduplicated and encrypted copies, kept only on your computer (a folder or a connected drive).
- **Scheduled backups** with a `systemd` user timer (hourly by default), resumed after an interruption, with a grandfather-father-son
  retention policy and GNOME notifications.
- **Set-up wizard** with a recovery key, a status window, a backup history and preferences.
- **Secrets in your keyring:** the repository password never touches a file, a command line or the environment.
- **English and Spanish**, in the interface, the in-app help (F1) and the website; an About dialog; keyboard and screen reader support.
- **Packages** for Fedora, Rocky Linux and AlmaLinux, openSUSE, Debian, Ubuntu and Arch; a Nix flake with a Home Manager module;
  and a Flatpak (the Delta window, with its own timer started through the Background portal).
- **Documentation** at <https://delta.sincorchetes.tech>, in English and Spanish.

[0.2.0]: https://github.com/sincorchetes/delta/releases/tag/v0.2.0
[0.1.3]: https://github.com/sincorchetes/delta/releases/tag/v0.1.3
[0.1.2]: https://github.com/sincorchetes/delta/releases/tag/v0.1.2
[0.1.1]: https://github.com/sincorchetes/delta/releases/tag/v0.1.1
[0.1.0]: https://github.com/sincorchetes/delta/releases/tag/v0.1.0
