# Delta technical specifications

What Delta is on the inside, why it is made this way and how it is checked. It is the source of the "Technical specifications"
page of the website. The figures are from **2026-11-18**; when they change, update them here and in
`website/src/content/docs/technical.mdx` (and its `es/` version).

For context: the design and its decisions are in [`plan.md`](plan.md), the status in [`roadmap.md`](roadmap.md), the D-Bus
contract in [`dbus-api.md`](dbus-api.md) and the threat model in [`security.md`](security.md).

## At a glance

| | |
|---|---|
| Backup engine | BorgBackup ≥ 1.4, as a subprocess (argv, never a shell) |
| Language and toolkit | Python ≥ 3.12, PyGObject, GTK 4 ≥ 4.10, libadwaita ≥ 1.5 (GNOME 46 or newer) |
| Architecture | Clean Architecture in four layers; files of about 300 lines at most |
| Service | A user-session daemon over D-Bus (`io.github.sincorchetes.Delta.Service1`), with no privileges |
| Scheduling | `systemd --user` (native) or its own timer with the Background portal (Flatpak) |
| Secrets | libsecret (the desktop keyring); to Borg through file descriptor 3 |
| Destination | Only this computer: a folder or a connected drive |
| Languages | English and Spanish (gettext, domain `delta`) |
| License | GPL-3.0-or-later |

## How it is checked

Quality is measured, not claimed. Every figure comes from a command that can be repeated.

- **Automated tests.** More than 1,200 test functions in 113 files (898 unit, 112 integration, 211 GTK widget tests; a count of
  `def test_`, without expanding the parametrized cases). The integration tests use **a real Borg** on a temporary repository
  and a simulated D-Bus; the GTK ones run on a virtual display and never show a window.
- **100 % coverage of lines and branches**, required (`fail_under = 100`). No `# pragma: no cover` and no omitted files: if
  something cannot be tested, the code is simplified.
- **Mutation tests** with `mutmut` on the logic that decides what is restored, kept, refused or interpreted (`domain/`,
  `application/`, the parsing and the commands of Borg, the timer and the wizard). A mutant is a deliberate change to the code;
  if no test fails, that test was not watching anything. The result: **2,028 mutants, 2,020 detected, 7 timed out** (they count as
  detected: the change causes a loop) and **1 survivor**, which is equivalent (a `None` instead of a `False`, which Python treats
  the same). The pipeline fails if more than that one survive (`scripts/ci/check_mutants.sh`).
- **Tests of the repository itself:** that every visible text is translated, that the help is valid Mallard and its links exist,
  that the versions of all the packages match `meson.build`, that the Flatpak manifest asks for no more permissions than agreed,
  that the Home Manager module links what the session needs, and that the website has the same pages in both languages.
- **Meson validators:** `appstreamcli validate` for the AppStream and `desktop-file-validate` for the `.desktop` files.
- **CI** (`.github/workflows/ci.yml`): the tests, then the mutation tests, then the website build and its checks, then publishing
  (only from `main`). CodeQL runs in another workflow.
- **Each distribution's own libraries** (`.github/workflows/distros.yml`, by hand and once a week; it does not block a pull
  request): Fedora, Arch, openSUSE Tumbleweed, AlmaLinux 10, Rocky 10, Ubuntu 24.04 and Debian 13 install the packages they ship
  (`python3-gobject`, GTK, libadwaita, BorgBackup), with their own Python and no uv or PyPI, check the minimum base, build and run
  the suite; and the Nix flake is built. That is what a user of the distribution's package gets, as opposed to the pinned
  libraries of `pyproject.toml`, which are only for development, the Nix package and the Flatpak.
- **Packages** built and installed in clean containers: Fedora 44, Rocky 10, openSUSE Tumbleweed, Debian 13, Ubuntu 24.04 and Arch.

## Why BorgBackup

There is no measured comparison of Borg with other tools, and this document does not invent one: other modern backup tools also
deduplicate and encrypt. Borg was chosen **for what Delta needs**, and each point can be checked in the code:

1. **Every backup is a complete snapshot that can be queried by path.** Delta asks "what versions does this file have?" with
   `borg list --json-lines REPO::BACKUP PATH`, without unpacking anything. It is the basis of the versions window.
2. **Deduplication by content and incremental copies.** After the first one, only what changed is stored and identical data is
   stored once, also across different files. That is why it can back up every hour.
3. **Authenticated encryption from the start.** `repokey-blake2` (AES-256 with BLAKE2b authentication): the repository is always
   created encrypted, even if it is local, and Borg verifies every chunk it reads.
4. **Machine-readable output.** `--json`, `--json-lines` and `--log-json` let the progress and the results be read without
   interpreting text, which is what turns into D-Bus signals.
5. **It can be mounted as a folder.** `borg mount` (FUSE) allows "Browse as a folder" in Files.
6. **Checkpoints.** `--checkpoint-interval` limits what is lost on an interruption (Delta sets it to 300 s; Borg's default is
   1,800 s). It is an approximate limit: a very large file can stretch it.
7. **Local repositories without a server.** A folder or a disk: no accounts, host keys or credentials.
8. **It is in every distribution we package.** `borgbackup` installs from the repositories of Fedora, EPEL (Rocky and Alma),
   openSUSE, Debian, Ubuntu and Arch, so Delta's package does not carry Borg inside.

**Limits that are accepted:**
- A repository has **a single lock**: while it is mounted, `borg create` cannot write. That is why Delta interrupts or postpones
  the backup when a snapshot is opened, and does not leave hanging mounts (see `plan.md` §7).
- `borg list` per snapshot is slow with many backups; `ListVersions` does it once for each.
- Delta uses the command-line API of Borg 1.x. Borg 2 changes that API: reviewing it before migrating is pending.

## How a backup works

1. **Scheduling.** A `systemd --user` timer (every hour by default) or, in a Flatpak, the daemon's own timer, asks the daemon for a
   backup over D-Bus (`CreateBackup`). If the computer was off at the due time, one is made on start, like `Persistent=true`.
2. **One job at a time.** Each backup is a `BackupJob` with the states `pending → running → succeeded`, `warnings`, `interrupted`
   or `failed`; an invalid transition is an error.
3. **The command.** `borg create --json --stats --progress --log-json --checkpoint-interval=300 --exclude … REPO::BACKUP SOURCES`.
   The sources are the chosen folders or, if there are none, `$HOME`. If the user chose folders and none is valid, the backup
   **fails**: it never widens to all of `$HOME`. By default it excludes `~/.cache` and the trash.
4. **The key.** The repository password lives in libsecret and reaches Borg through a pipe (fd 3), only to the child process;
   never through argv, the environment or the disk.
5. **Retention.** After each backup, `borg prune` with a grandfather-father-son policy: 24 hourly, 7 daily, 4 weekly and
   12 monthly by default, configurable. A policy that keeps nothing is refused.
6. **Interruptions.** A marker file in `XDG_STATE_HOME` says that a backup is running. If the daemon starts and finds it, the
   earlier backup was interrupted and it is resumed; Borg's checkpoints limit what was lost.
7. **A notice.** A GNOME notification with the result; Borg's error message is cut to 300 characters.

### Restoring

- **Listing versions:** `borg list --json-lines` for each snapshot and path.
- **Preview:** `borg extract` into a private read-only folder, which is deleted when the window closes and when the daemon stops.
  In a Flatpak it goes to the application's cache, because the service and the window are two instances of the sandbox and only
  share that folder.
- **Restore as a copy** (the default) leaves the old version next to the original under another name. **Replace** first sets the
  current one aside and puts it back if anything fails. Paths are validated: absolute, without `..`, and inside the home folder
  after resolving symbolic links.
- **Browse as a folder:** `borg mount -f`, only in the native install. The daemon interrupts the backup, postpones it, watches
  that the folder is being used and unmounts (`fusermount3 -u -z`) on close, suspend, lock or lack of use.

## Architecture in a line

`ui → application → domain ← infrastructure`: the domain is pure (no I/O, GTK or D-Bus), the use cases orchestrate **ports**
(`BackupEngine`, `SecretStore`, `Scheduler`, `SnapshotMounter`…) and the adapters (Borg, libsecret, systemd, Gio) are injected at
the edges. The clients (the app and the Nautilus extension) only talk to the daemon over D-Bus. That is what lets the Flatpak
replace systemd with a timer of its own without touching the domain.
