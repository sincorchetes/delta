# AGENTS.md — Delta

Instructions for agents working in this repository. Read them completely before touching code.
(People contributing by hand: [`CONTRIBUTING.md`](CONTRIBUTING.md) is the short version of this file.)

## What this is

**Delta**: a file "time travel" system (like macOS Time Machine), fully integrated with GNOME and Nautilus, with a
**BorgBackup** backup engine (incremental, deduplicated, encrypted). Backups are stored only **on the computer** (a folder or a
connected drive).

Living documents:

- `docs/plan.md` — the design and the architecture decisions (the source of truth).
- `docs/technical.md` — the technical specifications: how it is tested (with figures), why Borg and how backups work.
  **If the figures or the behavior change, update it together with the `technical.mdx` pages of the website.**
- `docs/roadmap.md` — milestones M0–M7 and their status. **Update it when you close a milestone.**
- `TODO.md` — what is missing for the next release, and what was deferred on purpose. **Keep it up to date with every change.**

Convention for `docs/`: the documents are in **American English** and their names are **lowercase with hyphens** (`plan.md`,
`dbus-api.md`). The files in the root that GitHub recognizes (`README.md`, `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`,
`CHANGELOG.md`) keep their uppercase names, which is what the platform looks for.

Current status: **M0, M1, M2, M3, M4, M5 and M6 completed** (the Borg engine; a complete daemon: secrets in the keyring, a systemd
scheduler, notifications, resuming after an interruption, a Nix package with a Home Manager module; and the GTK4 app: a wizard with a
local destination, a status window, a history and preferences). Deferred from M3 (details in `docs/roadmap.md`): "Unlock…" on
screen and a size column in the history (mounting a backup was done in M5). **M4 (the Nautilus extension)** is closed: a menu on files
and folders, a versions window with a preview (image, text, video, audio) and a folder browser, and a column and an emblem for the
backup state. **M5 (browsing backups as a folder with `borg mount`)** is closed, in the native variant only: the daemon interrupts the
backup when a folder is opened, postpones it, closes the folder on suspend, lock or lack of use, and `CanMount` hides it in a
Flatpak. **M6 (the time window)** is closed: the versions window compares each entry with the disk, filters by changes, searches
by name, restores rows and recovers what was deleted. Next: **M7 (polish and the 1.0 release)**, in progress.

## Architecture rules (non-negotiable)

- Clean Architecture in 4 layers: `domain` (pure, no I/O, GTK or D-Bus) → `application` (use cases, orchestrates ports) →
  `infrastructure` (borg, gio, libsecret, fuse, systemd) → `daemon` / `ui` / `nautilus`. Dependencies only point inward;
  injection at the edges.
- **About 300 lines per file at most.** One responsibility per module.
- A single stack: **Python 3 and PyGObject**. No intermediate shells: subprocesses always with `Gio.Subprocess` and argv
  (never `shell=True`).
- Do not reinvent the platform: scheduling with `systemd --user` timers, XDG autostart, config in GSettings and `XDG_*`, secrets
  in **libsecret** (never in a plain file or in GSettings), `Gio.Notification` notifications.
- No fork of Nautilus: the integration is a `nautilus-python` extension and a GTK4 window (see plan.md §7; the GVfs backend of the
  original plan was replaced by "Browse as a folder", see `docs/roadmap.md`, M5).
- **Portable to Flatpak** (without rewrites): no host paths or binaries (`/usr/bin/...`, `secret-tool`, `BORG_PASSCOMMAND`)
  outside their adapter; systemd, the keyring and any desktop capability come in through ports (`Scheduler`, `SecretStore`). The
  clients (the UI, the Nautilus extension) only talk to the daemon over D-Bus.
- Comments: only the strictly necessary ones; the code and the tests document themselves. Short docstrings stating the purpose
  in public modules.
- Tests are **mandatory** with every change: unit tests (pytest) in the domain and application layers; integration tests where
  they apply (a real Borg in tmp, dbusmock). Nothing is taken for granted without checking: build, tests and a smoke test of the
  scenario.
- Follow the GNOME developer guidelines: https://developer.gnome.org/documentation/
- **Multi-language (gettext, domain `delta`)**: every user-visible string goes through `delta.i18n._()` / `ngettext()`; the files
  with strings are listed in `po/POTFILES.in` and each language in `po/LINGUAS`. Code and identifiers are written in English;
  Spanish (`es`) is the first translation.

## Fixed namespaces

The D-Bus bus and interface `io.github.sincorchetes.Delta.Service1` (the object `/io/github/sincorchetes/Delta/Service1`) ·
GSettings `io.github.sincorchetes.Delta` · the GVfs URI `delta://` (reserved; the GVfs backend is deferred) · the binaries
`delta-*` · the Python package `delta` (a src layout in `src/delta/`).

The application identifier: **`io.github.sincorchetes.Delta`** (decided on 2026-11-17). `org.gnome.*` is the namespace of the GNOME
project itself and Flathub does not accept it from third parties; a Flatpak can only own D-Bus names that start with its
identifier, which is why the service is `io.github.sincorchetes.Delta.Service1`. **Exception:** the libsecret schema
(`infrastructure/libsecret_store.py`) is still called `org.gnome.Delta`: it is the name under which the passwords were stored,
and changing it would leave people without access to their backups.

## Development environment (devenv + Poetry/uv)

- **devenv (Nix) only for system libraries** (glib, GTK4, libadwaita, borg, nautilus, meson, ninja, gcc…). Adding nixpkgs
  `python3Packages` to the project is **forbidden**.
- **Python dependencies: Poetry (PEP 621 in `pyproject.toml`) and uv** (the environment `.devenv/state/venv`). `uv.lock` and
  `devenv.lock` are versioned.
- Enter with `devenv shell`. The devenv scripts: `sync`, `build`, `test`, `cov` (tests with coverage). Direct commands:
  `sh scripts/sync-venv.sh`, `uv run pytest`.

### The Nix package (`flake.nix`, `nix/`)

It is for **installing** Delta, not for developing it (that is devenv). The Python libraries (PyGObject, pycairo) are pinned in
`nix/python.nix` to the same versions and hashes as `uv.lock`; nixpkgs's are not used. If `uv.lock` changes, update
`nix/python.nix`. New files have to be added to git so that the flake sees them.

### Known traps (do not "fix" what already works)

1. **The GNOME sdists are built without build isolation** (`[tool.uv] no-build-isolation = true`) against the system libraries.
   That is why `scripts/sync-venv.sh` syncs in **3 phases**: toolchain → pycairo → pygobject/dbus-python. Do not collapse it into a
   single `uv sync`: pycairo has to be installed before PyGObject is built (`#include <py3cairo.h>`).
2. **Do not add `ninja`, `meson` or `patchelf` as PyPI dependencies**: their wheels are generic binaries that do not run on NixOS.
   They come from devenv/CI (dnf).
3. The real venv is `.devenv/state/venv` (devenv exports `UV_PROJECT_ENVIRONMENT`); outside devenv it is `./.venv`. The sync
   script already resolves it — always use it instead of a bare `uv sync`.
4. If the environment inherits a foreign `VIRTUAL_ENV`, ignore it (`unset VIRTUAL_ENV`); uv warns about it and uses the project's.
5. Importing `gi` in tests or the interpreter requires the venv (`uv run …`), not Nix's python3.

## CI

`.github/workflows/ci.yml`, in this order: the tests (a devenv job: lint, build, pytest with coverage) → the **mutation tests**
(`scripts/ci/check_mutants.sh`: it fails if more than one mutant survives, the known equivalent one) → the **website** (it builds
the site and checks its pages) → **publishing** (only on `main`). The packages for each distribution are not built here: OBS builds
them when a tag is published. **CodeQL** (`.github/workflows/codeql.yml`) analyzes, in another workflow, the Python code and the
workflows themselves, on every PR, on `main` and once a week.

**The system libraries of each distribution** are checked in another workflow, `.github/workflows/distros.yml`, which does not block
a pull request: you run it by hand, and it runs by itself once a week. It covers Fedora, Arch, openSUSE Tumbleweed, AlmaLinux 10,
Rocky 10, Ubuntu 24.04 and Debian 13, plus a build of the Nix flake. Each distribution installs the packages it ships (its
`python3-gobject`, GTK, libadwaita, BorgBackup) with `scripts/ci/install-deps.sh`, with **no uv and nothing from PyPI**: it is what
a user of that distribution's package gets. It checks the minimum base with `scripts/ci/check_base.py` (GNOME 46: GTK 4.10,
libadwaita 1.5, Python 3.12), builds with Meson, validates the GSettings schema, the `.desktop` file and the AppStream
(`meson test`) and runs `python3 -m pytest`. The `pyproject.toml` and `uv.lock` pins are only for development (devenv), the Nix
package and the Flatpak; a Flatpak brings its own runtime and is not part of that check. Toolchain changes must keep devenv and the
distributions in parity; when you add a system dependency, add it to `install-deps.sh` too.

## Workflow

- `main` is the stable branch and the only one published from (the website and the version tags). Nobody pushes directly to
  `main`; the only exception is the first commit of the repository.
- Every change follows the same path: a **new branch from `main`** (`feature/…`, `fix/…`, `docs/…`) → a **pull request** → CI
  green → a squash merge → the branch is deleted.
- To merge, the jobs `devenv` (tests and mutants) and `web` must pass in the PR. The distributions workflow is a check, not a gate.
- A new version is one more PR: it raises the version in `meson.build`, `packaging/rpm/delta-backup.spec` (with its `%changelog`),
  `debian/changelog`, `packaging/arch/PKGBUILD`, `packaging/obs/_service` and `CHANGELOG.md` (`tests/unit/test_packaging.py` fails
  if they disagree) and, once in `main`, it is tagged `vX.Y.Z` (with the `v` attached to the number: `v0.1.0`, never `v.0.1.0`).
  The guide for contributors is in `CONTRIBUTING.md`.

## Definition of done

1. `sh scripts/sync-venv.sh && uv run pytest --cov` green inside `devenv shell`, with **100 % coverage** of lines and branches
   (`fail_under = 100`). No `# pragma: no cover` and no omitted files: if something cannot be tested, the code is simplified, not
   hidden. The widget tests (`tests/gtk/`) need a display; where there is none they are run with `xvfb-run -a`. They never show
   windows or dialogs.
2. `meson setup build && meson compile -C build` green.
3. A valid GSettings schema if `data/` was touched.
4. The affected user scenario, really exercised (e.g. a D-Bus smoke test with `dbus-run-session`), not just imports and compilation.
5. `TODO.md` and `docs/roadmap.md` updated where it applies.
6. No temporary files of the agent itself in the repo (`build/`, `.venv/` and `.devenv/` are ignored).
