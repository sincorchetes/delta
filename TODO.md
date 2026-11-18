# TODO — Delta

What is missing before the 0.1.0 release, and what was deferred on purpose. The design is in [`docs/plan.md`](docs/plan.md)
and the status of each milestone in [`docs/roadmap.md`](docs/roadmap.md).

**Done and verified (2026-11-18):** milestones M0–M6, and M7 except for what is listed below. The tests pass at 100 % of lines and
branches; the mutation tests leave one equivalent survivor and seven timeouts; the website builds. Packages named `delta-backup`
were built and installed in clean containers on Fedora 44, Rocky 10, openSUSE Tumbleweed, Debian 13, Ubuntu 24.04 and Arch. The
Flatpak was built and tried on Fedora.

## 1. Publish the repository (the maintainer)

- [ ] Restart the repository so that the old recovery key is not in its history (it is in the commits `293c3c2` and `d939fe1`;
      it is already gone from the tree). Keep a copy of the old `.git` outside the repository.
- [ ] Push the first commit to `main` and make the repository public.
- [ ] Tag `v0.1.0` (no dot after the `v`), set the release date in `CHANGELOG.md` and create the GitHub Release from its notes.
- [ ] Set the real `sha256sums` in `packaging/arch/PKGBUILD` (it is `SKIP` now) and try the download from the tag with `makepkg`.

## 2. Configure GitHub

Do it after the first CI run, so that the names of the checks exist.

- [ ] **Ruleset for `main`:** target the default branch; require a pull request (0 approvals, squash only); require the checks
      `devenv (tests, quality, Sonar)` and `website (build and check)` and an up-to-date branch; require linear history;
      block deletions and force pushes. Add *Require code scanning results* once CodeQL has run.
- [ ] **Ruleset for the tags `v*`:** restrict updates and deletions and block force pushes; bypass for the repository admin role.
- [ ] **Settings:** description, website and topics; squash merging only and delete branches after merging; workflow permissions
      read-only; approval for first-time contributors; a social preview image.
- [ ] **Code security:** Dependabot alerts and security updates, secret scanning with push protection, private vulnerability
      reporting. Leave CodeQL's *default setup* off: the workflow `.github/workflows/codeql.yml` does it.
- [ ] **Pages:** source *GitHub Actions*; the custom domain `delta.sincorchetes.tech`; a DNS `CNAME` from `delta` to
      `sincorchetes.github.io`; then *Enforce HTTPS*; limit the `github-pages` environment to `main`.
- [ ] **SonarQube Cloud:** create the project `sincorchetes_delta` in the organization `sincorchetes`, turn its *Automatic Analysis*
      off and add the `SONAR_TOKEN` secret.

## 3. Check the first real CI run

- [ ] `ruff` with the version from devenv's nixpkgs (it was only tried with a newer ruff from another project).
- [ ] The mutation step ends with `surviving mutants: 1 (allowed: 1)`.
- [ ] `devenv` passes from scratch now that `scripts/sync-venv.sh` installs the build tools before the project.
- [ ] Run the **Distributions** workflow by hand (*Actions → Distributions → Run workflow*): the seven distributions and the Nix
      flake, each with its own libraries. The package names in `scripts/ci/install-deps.sh` were written from memory; fix
      what the first run reports.
- [ ] Dependabot opened a pull request that bumps `typescript` from 5 to 7 (a major version) in `website/`: do not merge it
      blindly (`astro check` may not support it); close it, or ignore major versions of `typescript` in `dependabot.yml`.
- [ ] CodeQL: the version of the actions (`@v4` was written from memory) and the checks `CodeQL (python)` and `CodeQL (actions)`.
- [x] Dependabot accepts the `bun` ecosystem (it opened a pull request for `website/`).
- [ ] The two issue forms show up under *Issues → New issue*.
- [ ] The website is deployed from `main`.

## 4. Release channels (after the tag)

- [x] **OBS, the project:** `home:sincorchetes:delta` exists, with the repositories `Fedora_43`, `Fedora_44`,
      `openSUSE_Tumbleweed`, `RockyLinux_10` and `AlmaLinux_10` (see `packaging/obs/README.md`). In the project's *Meta* tab,
      rename the repository still called `EL_10` to `RockyLinux_10`.
- [ ] **OBS, the package:** after the tag, upload `delta-backup.spec` and `_service` and check that the five repositories build.
- [ ] **OBS, Rocky and Alma:** install the package from each repository in a clean Rocky 10 and a clean AlmaLinux 10 container
      (the build environments were not tried yet; if something is `unresolvable`, the missing path goes in the repository's
      paths).
- [ ] **OBS, Debian and Ubuntu:** a second phase: add the repositories and package the `debian/` files for OBS.
- [ ] Update the installation page of the website with the real repository URLs, once the builds pass.
- [ ] **AUR:** publish `delta-backup` from `packaging/arch/PKGBUILD`.
- [ ] **Flathub:** the Python modules from pinned sources without network access (`flatpak-pip-generator`); see
      `flatpak/README.md`.

## 5. Try it on a real system

Building and importing in a clean container is not the same as running it.

- [ ] Install each package and run it: the service starts, the window opens, and a backup and a restore work.
- [ ] A pass with a screen reader (Orca) and with the keyboard only.
- [ ] Flatpak: the background permission with the portals active (`services.flatpak.enable = true` on NixOS).
- [ ] The Nautilus menu entry appears only once after `home-manager switch` (the extension used to be loaded twice).

## 6. Cleanup

- [ ] Split by responsibility the files over about 300 lines, which `AGENTS.md` asks to avoid:
      `tests/gtk/` (`test_folder_browser`, `test_panes_and_dialogs`, `test_small_widgets`, `test_status_window`,
      `test_versions_window`, `test_wizard`), `tests/unit/` (`test_browse_controller`, `test_daemon_wiring`,
      `test_infrastructure_edges`, `test_nautilus_extension`, `test_restore_beside`, `test_version_preview`) and
      `scripts/smoke_session.py`.
- [ ] Optional: rename the local project directory from `gnome-time-machine` to `delta`.

## Deferred on purpose (after 0.1.0)

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
- After each Dependabot pull request that touches `uv.lock`, update `nix/python.nix` in step with it.
