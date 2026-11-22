# TODO — Delta

What is missing, and what was deferred on purpose. The design is in [`docs/plan.md`](docs/plan.md) and the status of each
milestone in [`docs/roadmap.md`](docs/roadmap.md).

**Done and verified (2026-11-20):** milestones M0–M6, and M7 except for what is listed below. Version 0.1.3 is published: the
GitHub Release with its Flatpak bundle, the AUR and the openSUSE Build Service repositories (Fedora 43 and 44, Rocky 10,
AlmaLinux 10, openSUSE Tumbleweed, Debian 13 and Ubuntu 26.04 and 26.10) are all made by pushing the tag, and on each of the
eight distributions the package is installed from its repository in a clean container and its daemon makes a backup and restores a
file (*Package smoke*). That check found that 0.1.2 did not start its daemon on Fedora 43, Debian 13, Rocky 10 and AlmaLinux 10
(`GLibUnix.signal_add` only exists in the newest GLib), which every test missed because they replace GLib with a stand-in: it is
what 0.1.3 fixes. The tests pass at 100 % of lines and branches; the mutation tests leave one equivalent survivor; the website
builds and is deployed from `main`.

## 1. Publish the repository (the maintainer)

- [x] The repository was restarted, so the old recovery key is not in its history; it is public, and `v0.1.0` was tagged and
      released.
- [ ] Treat the old recovery key as burned: it was in the history of the first repository. Replace it wherever a backup was
      made with it.
- [x] The real `sha256sums` goes into the AUR by itself on each tag (`packaging/arch/PKGBUILD` keeps `SKIP`).

## 2. Configure GitHub

- [x] **Ruleset for `main`** and **ruleset for the tags `v*`** (`releases-tag`): both active.
- [x] **Settings:** description, website and topics; squash merging only.
- [ ] **Settings, still to check:** delete branches automatically after merging (it is off; `gh pr merge --delete-branch` does it),
      workflow permissions read-only, approval for first-time contributors, a social preview image.
- [x] **Code security:** Dependabot security updates, secret scanning and push protection.
- [ ] **Code security, still to check:** Dependabot alerts and private vulnerability reporting. Leave CodeQL's *default setup* off:
      the workflow `.github/workflows/codeql.yml` does it.
- [x] **Pages:** source *GitHub Actions* and the custom domain `delta.sincorchetes.tech`.
- [ ] **Pages:** GitHub reports no certificate of its own for the domain (*Enforce HTTPS* is off), although the site is served
      over HTTPS. Check who serves it (a proxy such as Cloudflare would) and that `http://` redirects to `https://`. Limit the
      `github-pages` environment to `main`.
- [x] **SonarQube Cloud:** the project `sincorchetes_delta` analyzes on every change to the code (the secret `SONAR_TOKEN`).
- [x] **SonarQube Cloud:** mark the six `--no-build` hotspots of `scripts/sync-venv.sh` and `scripts/ci/check_mutants.sh` as *Safe*:
      the GNOME sdists have to be built against the system libraries (see "Known traps" in `AGENTS.md`).
- [x] **Release credentials:** the environment `release` (limited to `main` and the tags `v*`) has the AUR key and the OBS token.

## 3. Check the CI

- [x] `ruff`, the mutation step (one allowed survivor) and `devenv` from scratch pass in the CI; CodeQL runs on `python` and
      `actions`; the website is deployed from `main`; Dependabot works for `uv`, `bun` and the actions (it ignores major versions of
      `typescript`).
- [x] The **Distributions** workflow runs green on Fedora, Arch, openSUSE Tumbleweed, AlmaLinux 10, Rocky 10, Ubuntu 26.04 and
      26.10, Debian 13 and the Nix flake, each with its own libraries. Its first run found, besides the package names: the
      keyring daemon needs `IPC_LOCK` in a container (Fedora, Arch); Enterprise Linux 10 has no Xvfb (`xwfb-run` stands in) and keeps
      `python3-dbusmock` in the repository `devel`; and GTK aborts the whole process, not just the test, when the GStreamer
      plugins or a GL library are missing.
- [x] **Distributions, the Nix job** builds the package, checks the flake and builds a minimal NixOS system with the module, as a
      flake module and imported by path with no flake, and checks its user units, its profile and the settings schema
      (`scripts/ci/check_nixos_module.sh`). It does not start the session: that needs a VM (`nixosTest`).
- [x] **GStreamer in the packages:** the RPM, the `.deb` and the PKGBUILD recommend the base and good plugins that the preview of a
      video or audio needs (the Nix package already listed them). The Fedora, Debian and Ubuntu names were tried by the
      workflow; the openSUSE and Arch ones are the usual names, not tried.
- [x] **GStreamer, when it is missing:** a recommendation can be skipped, and then GTK ends the whole program when the preview of
      a video is made, which Python cannot catch. Delta tries to make the player in a process of its own, once, and offers the file
      to its own application where that fails; the job *Ubuntu without the GStreamer plugins* proves both halves (the premise
      and the probe).
- [ ] **GTK 4.16** (Rocky and AlmaLinux 10) measures the `FlowBox` of the rows of buttons as one button wide, so two tests of how
      the row wraps are skipped before GTK 4.18; look at how it behaves in a real window with a long translation.
- [x] **The widget tests printed 52 GTK and libadwaita criticals** on every distribution: 51 were windows given to an application
      that had not started up, and one a test that laid a page out twice. Neither was a fault of the application; both are fixed,
      and the workflow now prints none.
- [x] **Nix on two channels:** the Distributions workflow builds the package and the NixOS module on `nixos-unstable` and
      `nixos-26.05` with the libraries of each (no `uv.lock` pins), and both are green. When `nixos-26.11` is out, move the stable
      leg to it.
- [x] **Package smoke** (`package-smoke.yml`): the eight distributions install the package from its repository, make a backup and
      restore a file, and all pass with 0.1.3. After a release it waits (up to three hours: Fedora, with two architectures, took more
      than 90 minutes to publish) for OBS to build the version of the tag. It does not cover the AUR (Arch builds its package from
      source, so there is nothing to install from a repository) or the Flatpak.
- [x] **Distributions, start the daemon for real:** the tests replace GLib and the bus with stand-ins, so a daemon that dies at
      startup passed them. Each job now runs `scripts/ci/package_smoke.py --source` (the daemon that Meson installs, with the
      distribution's own GLib, keyring and Borg: a repository, a backup and a restore), and then the window of the versions of a
      file against it (`--window`, under `xvfb-run` or `xwfb-run`): it must stay open with no traceback and no GLib critical.
- [ ] **Package smoke, the window of the installed package:** the same `--window` in *Package smoke*, against the package of the
      repository. It needs a virtual display in each clean container (Xvfb is not in Enterprise Linux 10: `xwfb-run`, from EPEL).
- [ ] **Flatpak smoke:** the bundle is built and attached, never run. Install it in a job and make a backup and a restore.
- [ ] **Type checking** in the CI (the IDE already shows what Pyright says): fix a baseline first, then keep it from growing.
- [x] **Checks that keep bugs out:** the widget tests fail on any GLib critical (`tests/gtk/conftest.py`); names that break careless
      code are backed up and restored with a real Borg; properties of the paths, the readers of Borg's output and the schedule
      are tested with `hypothesis`; every workflow is read as YAML (`tests/unit/test_workflows_yaml.py`); Distributions runs on the
      pull requests that touch what a package builds.
- [ ] The two issue forms show up under *Issues → New issue*.

## 4. Release channels

- [x] **A release is published by pushing its tag** (`flatpak.yml` and `release.yml`): the GitHub Release with the notes of
      `CHANGELOG.md` and the Flatpak bundle, the AUR (the real checksum and `.SRCINFO`) and OBS (the branch `release` and a token
      that can only run the source service, which fetches the spec, the dsc, `debian/` and the tarball from git). How it is set up
      is in `packaging/obs/README.md` and `CONTRIBUTING.md`.
- [ ] **OBS, Ubuntu 24.04:** its repository built but was never published, so it was left out. Try it again.
- [x] **OBS, the test project** `home:sincorchetes:delta-test` was deleted, with its token.
- [x] **Flatpak:** built offline from pinned sources and attached to each release (`flatpak/`).
- [ ] **Flatpak, updates:** the bundle does not update by itself. A repository of its own (for instance in GitHub Pages) would, or
      OBS, which builds Flatpaks from a `flatpak.yaml` (its docs do not say whether it publishes a repository, or whether it has
      the GNOME 51 runtime).
- [ ] **Flathub:** left out on purpose for now. Its policy does not accept manifests with AI-assisted content, which this one has,
      and asks for a stable project with some history. Look at it again when the project has both.
- [x] **NixOS module** (`nixosModules.default`, `nix/nixos.nix`): `services.delta.enable` installs the package and
      `nautilus-python`, declares the user units, the D-Bus service and the settings schema. Tried in a VM with GNOME
      (`nixos-rebuild build-vm`), both importing the file from a `configuration.nix` without flakes and as
      `delta.nixosModules.default` from a flake: the timer, the daemon, the window and the menu of Files work.
- [x] **NixOS module on a real system:** tried in VMs and on the maintainer's own machine, with the rest of its configuration
      (the Home Manager module of Delta must be off there).

## 5. Try it on a real system

Building and importing in a clean container is not the same as running it.

- [ ] Install each package and run it: the window opens and Files shows its menu. (The service, a backup and a restore are
      checked by *Package smoke*.)
- [x] A pass with a screen reader (Orca): it works.
- [x] A pass with the keyboard only: it works.
- [ ] Flatpak: the background permission with the portals active (`services.flatpak.enable = true` on NixOS).
- [x] **A drive that is not connected, with a drive** (a loop device mounted with `udisksctl`, 2026-11-20): the window says "The
      drive with your backups is not connected", and another drive in the same place says "Your backups are not on this drive". The
      root of a freshly formatted ext4 drive (it holds only `lost+found`) is accepted by the wizard.
- [ ] **The other causes, with a drive:** a full one (`dd` into it until "No space left"), a read-only one (`sudo mount -o
      remount,ro`) and one without permission (`chmod 500` on the folder of the repository): the window and the single notification
      of each, and that the backup goes on by itself when it is put right. Also that mounting the drive starts the waiting backup,
      and a pull of a drive in the middle of a copy.
- [ ] **The identity of the repository** (written, not yet in a release): Delta remembers the identifier of the repository it made
      or adopted and notices another one in its place, even with the same passphrase, instead of backing up into it. Tested with a
      real Borg (another repository with the same and with another passphrase, and an older copy of the same one).
- [ ] The Nautilus menu entry appears only once after `home-manager switch` (the extension used to be loaded twice).

## 6. Cleanup

- [ ] Split by responsibility the files over about 300 lines, which `AGENTS.md` asks to avoid:
      `tests/gtk/` (`test_folder_browser`, `test_panes_and_dialogs`, `test_small_widgets`, `test_status_window`,
      `test_versions_window`, `test_wizard`), `tests/unit/` (`test_browse_controller`, `test_daemon_wiring`,
      `test_infrastructure_edges`, `test_nautilus_extension`, `test_restore_beside`, `test_version_preview`) and
      `scripts/smoke_session.py`.
- [ ] Optional: rename the local project directory from `gnome-time-machine` to `delta`.

## Deferred on purpose

- **Unlock repository** on screen: done with tests, but a real lock could never be provoked (Borg cleans the ones left by an
  abrupt shutdown).
- **A size column** in the history: `borg list` gives no sizes; check whether `borg info` gives them all in one call.
- **An image gallery** with a slider and an integrated player; cleaning previews by age instead of when the window closes.
- **Faster `ListVersions`** with many backups: a batch query or a persistent SQLite index (`docs/plan.md` §12).
- **Mutation tests** over `daemon/` and `infrastructure/` too (it needs a decision on which tests to run: many need a real Borg
  or D-Bus).
- **A drive that goes away while Borg is copying** is told as "not connected" when the place cannot be reached afterwards, but it
  was only tried with fakes, not by pulling a real drive in the middle of a copy. Unmounted places under `/mnt` are not
  recognized (anybody makes folders there by hand), only those under `/run/media` and `/media`.
- **Run backups as transient units** (`systemd-run --user`): they survive the daemon, with `Nice` and `IOSchedulingClass`, and log to
  the journal.
- **Borg 2:** review its API policy before migrating.
- **A `SourceSnapshot` port** to back up from a read-only BTRFS or ZFS snapshot (2.0).
- **A backup destination reached through a bind mount** inside the folders that are backed up: the repository is skipped by its
  path (and Borg skips its own by inode), so a second path to the same folder is not recognized.
- **Nix on a channel that is not tried:** only `nixos-unstable` and the current stable are built; an older one may not work.
