# Changelog

All notable changes to Delta are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[0.1.3]: https://github.com/sincorchetes/delta/releases/tag/v0.1.3
[0.1.2]: https://github.com/sincorchetes/delta/releases/tag/v0.1.2
[0.1.1]: https://github.com/sincorchetes/delta/releases/tag/v0.1.1
[0.1.0]: https://github.com/sincorchetes/delta/releases/tag/v0.1.0
