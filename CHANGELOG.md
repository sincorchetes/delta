# Changelog

All notable changes to Delta are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the versions follow [Semantic Versioning](https://semver.org/).

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

[0.1.2]: https://github.com/sincorchetes/delta/releases/tag/v0.1.2
[0.1.1]: https://github.com/sincorchetes/delta/releases/tag/v0.1.1
[0.1.0]: https://github.com/sincorchetes/delta/releases/tag/v0.1.0
