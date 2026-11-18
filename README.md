# Delta

Time travel for your files in GNOME. Delta shows how a file or a folder looked on any day, from Files (Nautilus) or
its own window, and restores it. Copies are made by [BorgBackup](https://www.borgbackup.org/): incremental,
deduplicated and encrypted. They stay on your computer, in a folder or on a connected drive.

- **Right-click in Files:** *Restore Previous Version…* on any file or folder, with a preview of each version.
- **Browse as a folder:** open a copy as a normal folder (native install).
- **Quiet:** scheduled with `systemd` user timers, passwords in the desktop keyring, notifications through GNOME.
- **Translated:** English and Spanish; the interface, the in-app help (F1) and the website.

Documentation, in English and Spanish: <https://delta.sincorchetes.tech>

## Install

Delta needs GNOME 46 or newer (libadwaita 1.5, GTK 4.10) and Python 3.12 or newer. It is published in a repository for
Fedora, Rocky Linux, AlmaLinux and openSUSE (built by the openSUSE Build Service), so your package manager installs it and
keeps it up to date, and in the AUR for Arch Linux. For Debian and Ubuntu you build the package. The recipes are in
[`packaging/`](packaging/) and [`debian/`](debian/); there is also a Nix flake with a Home Manager module and a Flatpak
manifest in [`flatpak/`](flatpak/). Step by step: <https://delta.sincorchetes.tech/install/>

## Development

Read [`AGENTS.md`](AGENTS.md) first: the architecture rules, the development environment (devenv, Poetry and uv) and
what "done" means. The design lives in [`docs/plan.md`](docs/plan.md), the milestones in
[`docs/roadmap.md`](docs/roadmap.md), and how it is tested, why it uses Borg and how a backup works in
[`docs/technical.md`](docs/technical.md) (also on the website, under *Technical specifications*).

```sh
devenv shell
sync        # Python dependencies
build       # meson setup and compile
test        # the test suite
cov         # the test suite with coverage (100 % of lines and branches is required)
```

## Licence

GPL-3.0-or-later. See [`LICENSE`](LICENSE) and, for what Delta builds on,
[`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).
