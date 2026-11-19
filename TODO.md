# TODO — Delta

What is missing, and what was deferred on purpose. The design is in [`docs/plan.md`](docs/plan.md) and the status of each
milestone in [`docs/roadmap.md`](docs/roadmap.md).

**Done and verified (2026-11-19):** milestones M0–M6, and M7 except for what is listed below. Version 0.1.2 is published: the
GitHub Release with its Flatpak bundle, the AUR and the openSUSE Build Service repositories (Fedora 43 and 44, Rocky 10,
AlmaLinux 10, openSUSE Tumbleweed, Debian 13 and Ubuntu 26.04 and 26.10) are all made by pushing the tag, and the packages were
installed in clean containers. The tests pass at 100 % of lines and branches; the mutation tests leave one equivalent survivor;
the website builds and is deployed from `main`.

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
- [ ] **SonarQube Cloud:** mark the six `--no-build` hotspots of `scripts/sync-venv.sh` and `scripts/ci/check_mutants.sh` as *Safe*:
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
- [ ] **Distributions, the Nix job** builds the package and checks the flake, but does not use the NixOS module: build a minimal
      NixOS system with it, with flakes and importing `nix/nixos.nix` by path, and check its units and its profile.
- [ ] **GStreamer in the packages:** the RPM, the `.deb` and the PKGBUILD do not declare the GStreamer plugins that the preview of
      a video or audio needs (only the Nix package lists them), and without them GTK aborts the process. Declare them as
      recommended (`Recommends:`, `optdepends`) once the names are checked in each distribution.
- [ ] **GTK 4.16** (Rocky and AlmaLinux 10) measures the `FlowBox` of the rows of buttons as one button wide, so two tests of how
      the row wraps are skipped before GTK 4.18; look at how it behaves in a real window with a long translation.
- [ ] **The widget tests print 52 GTK and libadwaita criticals** on every distribution (windows created before the application
      starts up, a widget added twice to a `PreferencesGroup`): the output was hidden until the workflow stopped capturing it. Some
      may point at a real mistake.
- [ ] The two issue forms show up under *Issues → New issue*.

## 4. Release channels

- [x] **A release is published by pushing its tag** (`flatpak.yml` and `release.yml`): the GitHub Release with the notes of
      `CHANGELOG.md` and the Flatpak bundle, the AUR (the real checksum and `.SRCINFO`) and OBS (the branch `release` and a token
      that can only run the source service, which fetches the spec, the dsc, `debian/` and the tarball from git). How it is set up
      is in `packaging/obs/README.md` and `CONTRIBUTING.md`.
- [ ] **OBS, Ubuntu 24.04:** its repository built but was never published, so it was left out. Try it again.
- [ ] **OBS, the test project** `home:sincorchetes:delta-test` and its token are no longer needed: delete them.
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
- [ ] **NixOS module on a real system:** only tried in VMs; `nixos-rebuild test --flake` on a machine with its own configuration
      would show how it lives with the rest of it (for instance, next to the Home Manager module, which must be off).

## 5. Try it on a real system

Building and importing in a clean container is not the same as running it.

- [ ] Install each package and run it: the service starts, the window opens, and a backup and a restore work.
- [x] A pass with a screen reader (Orca): it works.
- [ ] A pass with the keyboard only.
- [ ] Flatpak: the background permission with the portals active (`services.flatpak.enable = true` on NixOS).
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
- **Run backups as transient units** (`systemd-run --user`): they survive the daemon, with `Nice` and `IOSchedulingClass`, and log to
  the journal.
- **Borg 2:** review its API policy before migrating.
- **A `SourceSnapshot` port** to back up from a read-only BTRFS or ZFS snapshot (2.0).
- **A backup destination reached through a bind mount** inside the folders that are backed up: the repository is skipped by its
  path (and Borg skips its own by inode), so a second path to the same folder is not recognized.
- After each Dependabot pull request that touches `uv.lock`, update `nix/python.nix` in step with it.
