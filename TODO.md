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
- [x] **Settings:** branches are deleted after merging, workflow permissions are read-only and cannot approve pull requests
      (checked with the API, 2026-11-25).
- [ ] **Settings, still to check:** approval for first-time contributors (Settings → Actions → General; the API does not show it)
      and a social preview image.
- [x] **Code security:** Dependabot security updates, secret scanning and push protection.
- [x] **Code security:** Dependabot alerts and private vulnerability reporting are on (2026-11-25). Leave CodeQL's *default setup*
      off: the workflow `.github/workflows/codeql.yml` does it.
- [x] **Pages:** source *GitHub Actions* and the custom domain `delta.sincorchetes.tech`.
- [x] **Pages, HTTPS:** the domain is behind the Cloudflare proxy, which serves the certificate and redirects `http://` to
      `https://` (*Always Use HTTPS*); the minimum TLS version is 1.2. Its encryption mode is **Full**, not *Full (strict)*:
      GitHub has no certificate for the domain and gives its generic one, which *strict* rejects (error 526). GitHub reports no certificate of its own and *Enforce HTTPS*
      stays off **on purpose**: it cannot issue one behind a proxy, and forcing HTTPS at the origin too would make redirect loops.
      HSTS is left off until every subdomain is known to go over HTTPS.
- [ ] **Pages, still to check:** limit the `github-pages` environment to `main`; and that the domain is *verified* in the GitHub
      account (Settings → Pages → Add a domain, with a TXT record): the DNS has a wildcard `*` that points to `github.io`, so
      without verification anybody could serve a site from an invented subdomain.
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
- [x] **Flatpak smoke** (`scripts/ci/flatpak_smoke.sh`, in `flatpak.yml`): the bundle is installed and run, and BorgBackup works in the
      sandbox, the application is the version of the tree, the daemon owns its name on the bus and the window stays open without
      criticals.
- [ ] **A backup inside the Flatpak, in CI:** the smoke does not make one, because the passphrase goes to the keyring through the
      Secret portal, which a runner does not have (it would need `xdg-desktop-portal` with a keyring backend).
- [x] **Type checking** in the CI (`pyright`, in the devenv job, in `basic` mode): PyGObject has no stubs, so `typings/gi/` types
      `gi.repository` as `Any` and what is checked is Delta's own code. The 9 real errors it found (a service, an engine and some
      jobs used as if they were never `None`) are fixed. Next: `standard` mode, and the tests (`include` only has `src`).
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
- [x] **The publication checks the tag first** (`scripts/ci/check_tag.sh`, in `release.yml` and `flatpak.yml`): a tag pushed before
      the version PR was merged (v0.2.0, once) made the AUR and the GitHub Release fail and OBS try to build it.
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
- [x] **The other causes, with a drive:** a full one, a read-only one and one without permission, the window and the single
      notification of each, that the backup goes on by itself when it is put right, that mounting the drive starts the waiting
      backup, and a failure of the device in the middle of a copy (a `dmsetup` `error` target under a loop device, 2026-11-24).
      That last one showed that ext4 refuses writes with `EROFS` while the mount stays `rw` (`emergency_ro`), so the probe cannot
      see it: the failed backup is what tells (the whole report of Borg is classified, not its one-line account).
- [ ] **The identity of the repository** (in 0.2.0, tried with a real Borg but not with real drives): Delta remembers the identifier of the repository it made
      or adopted and notices another one in its place, even with the same passphrase, instead of backing up into it. Tested with a
      real Borg (another repository with the same and with another passphrase, and an older copy of the same one).
- [ ] The Nautilus menu entry appears only once after `home-manager switch` (the extension used to be loaded twice).

## 6. Cleanup

- [ ] Split by responsibility the files over about 300 lines, which `AGENTS.md` asks to avoid:
      `tests/gtk/` (`test_folder_browser`, `test_panes_and_dialogs`, `test_small_widgets`, `test_status_window`,
      `test_versions_window`, `test_wizard`), `tests/unit/` (`test_browse_controller`, `test_daemon_wiring`,
      `test_infrastructure_edges`, `test_nautilus_extension`, `test_restore_beside`, `test_version_preview`) and
      `scripts/smoke_session.py`.
- [x] The bytecode of a working copy no longer goes into what Meson installs (`__pycache__` had to be named for each subpackage).
- [ ] Optional: rename the local project directory from `gnome-time-machine` to `delta`.

## Deferred on purpose

- **Unlock repository** on screen: done with tests, but a real lock could never be provoked (Borg cleans the ones left by an
  abrupt shutdown).
- **A size column** in the history: `borg list` gives no sizes; check whether `borg info` gives them all in one call.
- **An image gallery** with a slider and an integrated player; cleaning previews by age instead of when the window closes.
- **Faster `ListVersions`** with many backups: a batch query or a persistent SQLite index (`docs/plan.md` §12).
- **Mutation tests, the rest of `daemon/` and `infrastructure/`:** the rules are mutated now (the runner of jobs and its signals on
  the bus, the task of a backup, the cache of listings, the destination, the settings, the next run...). Left out, because
  `mutmut` runs only the unit tests and these are judged by integration tests or the real system: the handlers of the D-Bus calls
  (`job_calls`, `query_calls`), the wiring (`composition`, `main`), and the adapters (`borg_runner`, `borg_mounter`, `libsecret_store`,
  `systemd_scheduler`, `background_portal`, `session_events`, `ui_launcher`, `gio_notifier`). `gio_notifier` would need each message
  asserted exactly. `sh scripts/ci/mutants_by_module.sh` shows where the survivors are after a run.
- **A drive that goes away while Borg is copying** was tried with a device-mapper failure under a loop device, not with a physical
  drive that is pulled. Unmounted places under `/mnt` are not recognized (anybody makes folders there by hand), only those under
  `/run/media` and `/media`.
- **The check of the data of every backup** (`borg check` without `--repository-only`, or with `--verify-data`): it reads every
  chunk, so it takes hours on a large repository. It would be an option of «Check backups», with progress and cancel, and a
  warning that it is slow. «Check backups» today only checks that the files of the repository can be read.
- **A notification when a check ends**, for when the window was closed (a check can take long): `BackupNotifications` has no kind
  for it yet.
- **The state of the drive (SMART) through UDisks2**, as a hint only («the drive says it may fail»), never blocking anything:
  `Drive.Ata` and `Nvme.Controller` on the system bus, behind a port, like the scheduler and the keyring; no `smartctl` (it needs
  root and a host binary). Native first. In a Flatpak it needs `--system-talk-name=org.freedesktop.UDisks2` (find out whether
  Flathub accepts it for this) and a way from the repository folder to its block device that the sandbox may hide (its
  `mountinfo` is not the host's): hide it there, as `CanMount` is, until both are proven. Many USB drives do not pass SMART
  through their adapter, so «unknown» has to be a normal answer, and «SMART passed» must not read as «the drive is fine».
- **Run backups as transient units** (`systemd-run --user`): they survive the daemon, with `Nice` and `IOSchedulingClass`, and log to
  the journal.
- **Borg 2:** review its API policy before migrating.
- **A `SourceSnapshot` port** to back up from a read-only BTRFS or ZFS snapshot (2.0).
- **A backup destination reached through a bind mount** inside the folders that are backed up: the repository is skipped by its
  path (and Borg skips its own by inode), so a second path to the same folder is not recognized.
- **Nix on a channel that is not tried:** only `nixos-unstable` and the current stable are built; an older one may not work.
