# Delta — Development plan

> A file "time travel" system, fully integrated with GNOME and Nautilus, in the style of macOS Time Machine,
> with a backup engine based on BorgBackup.

**Date:** 2026-11-09 (last reviewed 2026-11-18)
**Status:** the design reference. It started as the initial plan and keeps its decisions, with the changes made along the way
marked in the text. The current status of each milestone is in [`roadmap.md`](roadmap.md).

---

## 1. Vision and goals

Reproduce the **Time Machine (macOS)** experience in GNOME:

- From **Nautilus**, the user can go back to earlier versions of a file or folder (a context menu and a temporary view) and
  restore them with one click.
- Backups are made by **BorgBackup**: deduplication, compression, encryption, incremental copies. The repositories are
  **local** (a folder or a connected drive).
- Native integration with the desktop: **D-Bus, XDG, systemd (the user session), Gio/GTK 4, libadwaita, GVfs**. Schedulers,
  autostart and notifications are not reinvented: the platform's standards are used.

### Functional goals (MVP → complete)

1. Create and configure Borg repositories (local, encrypted).
2. Scheduled incremental backups (a user systemd timer) and on demand.
3. A Nautilus extension: "Restore Previous Version…" per file or folder.
4. A time-travel view in the style of Time Machine: a **GVfs** backend (`delta://`) browsable directly in Nautilus, plus a
   temporary window with a snapshot slider (see §7).
5. GNOME notifications about the state of the backups (success, error, space).
6. Automatic pruning and retention (`borg prune` with a configurable GFS policy).
7. Export and mount of archives (`borg mount` through FUSE) for free exploration.

## 2. Technology stack (GNOME, current version)

| Layer | Technology |
|---|---|
| Main language | **Python 3** (CPython ≥ 3.12) and **PyGObject** |
| UI | **GTK 4 and libadwaita** (the preferences app, the temporary window and the dialogs) |
| IPC | **D-Bus** (Gio.DBus), bus name `io.github.sincorchetes.Delta.Service1` |
| Lifecycle | **systemd --user**: a D-Bus-activated service and a `timer` for the backups |
| Autostart / session | **XDG Autostart** (`~/.config/autostart`), the XDG Base Directory for config, cache and data |
| Nautilus extension | **nautilus-python** (the `Nautilus.MenuProvider`, `InfoProvider` and `ColumnProvider` API) |
| Browsing snapshots | A **GVfs backend** of its own (`gvfsd-delta`) over `borg mount` (FUSE) |
| Backup engine | **BorgBackup ≥ 1.4** run as a subprocess (json/log parsed) |
| Config | `GSettings` (the `io.github.sincorchetes.Delta` schema) and secrets in **libsecret/Keyring** |
| Build | **Meson** (the GNOME standard), an optional Flatpak manifest (with `finish-args` for borg/FUSE) |
| Development environment | **devenv** (Nix) only for system libraries (glib, GTK4, borg, nautilus…) |
| Python dependencies | **Poetry** (the definition, PEP 621 in `pyproject.toml`) and **uv** (the `.venv` and the installation); no Python packages from nixpkgs |
| Tests | **pytest**, `python-dbusmock`, `dogtail` (UI), integration tests with a real Borg repository on tmpfs |

> Language decision: Python allows sharing the stack with `nautilus-python` and with Borg's own ecosystem, and PyGObject gives
> full access to GTK4/libadwaita/Gio/GVfs. A daemon in Rust is rejected so as not to duplicate stacks.

## 3. Architecture (Clean Architecture)

The dependency rule: `ui → application → domain ← infrastructure`. The domain knows neither D-Bus, nor Borg, nor GTK.
**About 300 lines per file at most**, one responsibility per module, pure functions in the domain, dependency injection at the edges.

```
┌─────────────────────────── GNOME Session (user) ──────────────────────────────┐
│                                                                                │
│  Nautilus                 GTK4/libadwaita app          systemd --user          │
│  ┌──────────────────┐    ┌──────────────────────┐     ┌────────────────────┐  │
│  │ Python extension  │    │ preferences/wizard   │     │ delta.             │  │
│  │ (context menu,    │    │ temporary window     │     │ service (daemon)   │  │
│  │ emblems)          │    │ (snapshot slider)    │     │ delta.             │  │
│  └────────┬─────────┘    └──────────┬───────────┘     │ timer (schedule)   │  │
│           │                         │                  └─────────┬──────────┘  │
│           │  GVfs: delta://         │                            │             │
│  ┌────────▼─────────┐               │                            │             │
│  │ gvfsd-delta      │               │                            │             │
│  │ (GVfs backend →  │               │                            │             │
│  │  borg mount/FUSE)│               │                            │             │
│  └────────┬─────────┘               │                            │             │
│           └────────────┬────────────┴────────────────────────────┘             │
│                        │ D-Bus (session)                                       │
│              io.github.sincorchetes.Delta.Service1                             │
│                        │                                                       │
│            ┌───────────▼────────────┐                                          │
│            │   DAEMON (Gio.DBus)    │  ← systemd user service, D-Bus activated │
│            ├────────────────────────┤                                          │
│            │ application/ use cases │  BackupService, RestoreService,          │
│            │                        │  SnapshotService, PruneService           │
│            ├────────────────────────┤                                          │
│            │ domain/                │  Snapshot, Repository, RetentionPolicy,  │
│            │                        │  BackupJob, FileVersion (pure, no I/O)   │
│            ├────────────────────────┤                                          │
│            │ infrastructure/        │  BorgRunner (subprocess),                │
│            │                        │  SecretStore (libsecret), GSettingsConf, │
│            │                        │  NotificationAdapter (Gio.Notification), │
│            │                        │  FuseMounter, SystemdScheduler           │
│            └───────────┬────────────┘                                          │
│                        ▼                                                       │
│                 borg (CLI) ──► local repository (a folder or a drive)          │
└────────────────────────────────────────────────────────────────────────────────┘
```

### Repository structure

```
delta/
├── meson.build
├── data/
│   ├── io.github.sincorchetes.Delta.desktop.in
│   ├── io.github.sincorchetes.Delta.gschema.xml
│   ├── io.github.sincorchetes.Delta.Service1.service                # D-Bus activation
│   ├── systemd/delta.service                   # user service
│   ├── systemd/delta.timer                     # the backup schedule
│   └── icons/
├── src/
│   ├── delta/
│   │   ├── domain/         # entities and policies (no external dependencies)
│   │   ├── application/    # use cases / application services
│   │   ├── infrastructure/ # borg, gio, secret, fuse, systemd
│   │   ├── daemon/         # the D-Bus object, the service entry point
│   │   ├── ui/             # the GTK4/libadwaita app (preferences, temporary window)
│   │   ├── gvfs/           # the gvfsd-delta backend
│   │   └── nautilus/       # the nautilus-python extension
│   └── delta-daemon        # the entry point installed in libexec
├── tests/
│   ├── unit/
│   ├── integration/       # real borg and dbusmock
│   └── ui/                # dogtail
└── docs/
    ├── plan.md (this document)
    ├── dbus-api.md
    └── security.md
```

## 4. D-Bus API (draft)

The `io.github.sincorchetes.Delta.Service1` interface on the session bus:

```xml
<node>
  <interface name="io.github.sincorchetes.Delta.Service1">
    <method name="CreateBackup">
      <arg name="job_id" type="s" direction="out"/>
    </method>
    <method name="ListSnapshots">
      <arg name="snapshots" type="aa{sv}" direction="out"/> <!-- id, date, size -->
    </method>
    <method name="ListVersions">       <!-- the versions of one given path -->
      <arg name="path" type="s" direction="in"/>
      <arg name="versions" type="aa{sv}" direction="out"/>
    </method>
    <method name="Restore">
      <arg name="snapshot_id" type="s" direction="in"/>
      <arg name="source_path" type="s" direction="in"/>
      <arg name="target_path" type="s" direction="in"/>
      <arg name="job_id" type="s" direction="out"/>
    </method>
    <method name="MountSnapshot">
      <arg name="snapshot_id" type="s" direction="in"/>
      <arg name="mountpoint" type="s" direction="out"/>
    </method>
    <signal name="Progress">           <!-- job_id, percentage, phase -->
      <arg type="s"/><arg type="d"/><arg type="s"/>
    </signal>
    <signal name="BackupFinished">     <!-- job_id, ok, message -->
      <arg type="s"/><arg type="b"/><arg type="s"/>
    </signal>
    <property name="Status" type="s" access="read"/> <!-- idle|running|error -->
    <property name="LastBackup" type="t" access="read"/>
  </interface>
</node>
```

The detailed contract is in [`dbus-api.md`](dbus-api.md). The interface is versioned (`...1`) so that it can evolve compatibly.

## 5. Integration with systemd and XDG

- `delta.service` (user): `Type=dbus`, `BusName=io.github.sincorchetes.Delta.Service1`. The daemon starts by D-Bus
  activation, not by traditional autostart.
- `delta.timer` triggers `delta-backup.service` (a oneshot that calls `CreateBackup` over D-Bus). `OnCalendar=hourly` by
  default; configurable through GSettings → the daemon rewrites the `delta.timer.d/schedule.conf` drop-in in
  `XDG_CONFIG_HOME`, not the unit file.
- Scheduling is the `Scheduler` port (`application/ports.py`); `SystemdScheduler` is the first adapter. In a Flatpak
  `systemd --user` does not exist inside the sandbox: the alternative adapter (the Background portal or the daemon's own timer)
  is decided when packaging, without touching the domain.
- Config in `GSettings` and `XDG_CONFIG_HOME`; the Borg cache in `XDG_CACHE_HOME/borg`; passwords and passphrases **never in a
  plain file**: libsecret (GNOME Keyring), handed to Borg through a file descriptor (`BORG_PASSPHRASE_FD`), never through argv or
  the environment. If the user does not choose a password, the daemon generates a high-entropy one and records it in the keyring.
- Notifications with `Gio.Notification` (they appear in the notification center of GNOME Shell, with "View details" / "Retry"
  actions).

### UI (M3): identities and layers

- Two distinct GApplications: **`io.github.sincorchetes.Delta`** (the GTK app, `delta-ui`, a visible `.desktop`) and
  **`io.github.sincorchetes.Delta.Daemon`** (the daemon, a hidden `.desktop`, which the notifications hang from). Sharing an id
  would make launching the app delegate to the daemon, which has no window.
- The app only talks to the daemon over D-Bus (`delta.ui.client`) and reads GSettings for configuration. No Borg and no systemd
  in the UI.
- The presentation logic (what each state says, the wizard's validation) lives in modules without GTK (`delta.ui.status`, …) so
  it can be tested without a screen; the widgets (`delta.ui.window`) are a thin layer on top.

## 6. Integration with BorgBackup

- The `BorgRunner` layer: it builds and runs commands (`create --json`, `list --json`, `extract`, `prune`, `mount`) with
  structured parsing of the progress JSON → D-Bus signals.
- The default GFS retention policy: `--keep-hourly 24 --keep-daily 7 --keep-weekly 4 --keep-monthly 12`.
- Repositories: local only (`Repository` requires an absolute path).
- Sensible default exclusions (caches, `~/.cache`, trash cans), editable in preferences; patterns from borg-style files.
- Handling real errors: a locked repository, a missing passphrase, a full disk → domain states and actionable notifications.

## 7. Integration with Nautilus

**Adopted decision (a balance of maintainability, visualization and standards):** a combination of a **standard extension, a
GVfs backend of its own and a GTK4 temporary window**. A fork or patch of Nautilus is rejected: it means maintaining a patch
against every release, it breaks the user's update chain and it clashes with the upstream policy; the GVfs backend achieves 90 %
of the experience within the platform's standards.

**A. The standard extension (nautilus-python):**
- **The extension is minimal and does not import `delta`**: it runs inside Nautilus with the Python of `nautilus-python`, which
  is not the package's, and a failure in it would take Nautilus down with it. It only adds the menu and opens the app through a
  hidden `.desktop` (`io.github.sincorchetes.Delta.Versions.desktop`, `delta-ui --versions %f`); there are no host paths or
  binaries in it and it does not talk to the daemon. It looks for its translation in the `share/locale` of the XDG directories.
- A context menu on a file or folder (first delivery: a single file inside `$HOME`; folders come later):
  - "Restore Previous Version…" → opens **the app's versions window** (`delta-ui --versions`), with the list over D-Bus; it
    restores to a copy next to the original (`file (restored 2026-11-09).ext`) or replaces it, setting the current one aside first.
  - "Travel back in time" → opens the temporary window (see C) on the selected path.
- Emblems and state (`InfoProvider`): a mark on files covered by the backup.
- A "Last backup" column (`ColumnProvider`), optional.

**B. The GVfs backend (`gvfsd-delta`, URI `delta://`) — DEFERRED (2026-11-12):** measured with Borg 1.4.5: a mounted repository
blocks `borg create`, and a GVfs backend is C against GVfs's internal libraries (it does not fit "a single language, Python").
Browsing backups is covered by the versions window (`ListFolder`, `PreviewVersion`); the details are in `roadmap.md` (M5). What
follows is the original design, kept in case it is taken up again:
- Nautilus (and any GTK app) browses the snapshots **without patches**:
  - `delta:///` → the list of snapshots (each one a folder with a date).
  - `delta:///<snapshot>/path/to/file` → the content of the snapshot.
- Implemented over `borg mount` (FUSE) managed by the daemon, or reading over D-Bus if the mount is not active (the daemon
  activates it on demand).
- The full standard: dragging files to restore, thumbnails, search, "Open with…". GVfs is GNOME's official mechanism for
  virtual file systems (like `trash://` or `recent://`).

**C. The temporary window (GTK4/libadwaita) — the Time Machine experience:**
- It is launched from the Nautilus context menu or from the app.
- A view of the current folder over the GVfs backend plus a **snapshot slider at the bottom** (a time scale), with a file preview
  and a "Restore" / "Restore as a copy" button.
- A separate window rather than one embedded in Nautilus: it is the only visual route without patching Nautilus, and it keeps the
  app updatable.

**Future reevaluation:** if the experience requires it, proposing an upstream "temporal view" API or a minimal patch to Nautilus
can be considered; it is not a goal of 1.0.

## 8. Security

- The daemon runs in the **user session**, with no extra privileges; no polkit helpers unless a system mount is needed (not in
  the MVP).
- Passphrases in **libsecret**; never in GSettings or in files.
- Strict path validation in the D-Bus API (canonicalization, rejecting `..` outside the home folder, symlink checks) before
  invoking Borg.
- The GVfs backend only exposes the user's own data (mounts in `$XDG_RUNTIME_DIR/gvfs`, permissions 0700).
- Encrypted repositories (`repokey-blake2` by default) even locally.
- Polkit only if restoring system files is added (out of scope).
- No intermediate shell: `Gio.Subprocess` with argv, no `shell=True`.
- Flatpak sandboxing evaluated: Borg and FUSE need broad permissions; it is documented as a secondary distribution (the primary
  one: the native package). Decision (2026-11-16): two variants. The native one adds mounting backups (`borg mount`, the
  `SnapshotMounter` port, the `CanMount` capability); the Flatpak one does not mount and is managed only from Delta's UI. The
  details are in `roadmap.md` (M5).

The model of threats and guarantees that the code meets today is in [`security.md`](security.md).

## 9. Testing strategy

> The original plan. What is actually run, with its figures, is in [`technical.md`](technical.md): 100 % coverage of lines and
> branches, mutation tests, widget tests on a virtual display, and the pipeline.

**Unit (pytest, a coverage target of ≥ 85 % in domain/application):**
- Entities and retention policies (GFS), computing versions, parsing Borg's JSON, path validation, the job state machine.

**Integration:**
- `BorgRunner` against a real Borg repository in `tmp` (init → create ×N → modify → list → extract → prune) with deterministic
  synthetic datasets.
- The whole D-Bus API with `python-dbusmock` and, in CI, with a real session bus in a container (`dbus-run-session`).
- D-Bus activation and a user systemd unit in a container with systemd.
- The GVfs backend: enumerating `delta:///` and reading files with `Gio.File` against a mounted test repository.
- The Nautilus extension: loading the module with `Nautilus` stubs and checking menus and emblems; a smoke test in a VM with a real
  Nautilus (a headless session with Xvfb / `gnome-desktop-testing`).

**UI:** dogtail for the key flows (the first-repository wizard, restoring, the temporary window).

**E2E:** a complete scenario: create a file → back up → modify → restore the earlier version from the Nautilus menu, checking
content and permissions.

CI: GitHub Actions (or GitLab CI) with a GNOME container (`fedora:rawhide` or the Flatpak SDK's `image: gnome`), a matrix of
supported Borg versions.

## 10. Milestones

> The original milestones. M5 turned into "Browse backups as a folder" and the current status of each one is in
> [`roadmap.md`](roadmap.md).

| Milestone | Content | Acceptance criterion |
|---|---|---|
| M0 — Skeleton | Meson, GSettings, a systemd unit, an empty D-Bus daemon, CI | `gdbus introspect` shows the interface; CI is green |
| M1 — Borg engine | `BorgRunner`, the domain and integration tests | The create/list/extract/prune cycle is green in CI |
| M2 — Complete daemon | Use cases, the scheduler (timer), notifications | An hourly automatic backup works in a real session |
| M3 — GTK4 app | A repository wizard, preferences, status | An end-to-end configuration flow with dogtail |
| M4 — Nautilus extension | A context menu, restoring and emblems | Restoring from a right-click works (E2E) |
| M5 — GVfs backend | `gvfsd-delta` over `borg mount` | Browsing `delta:///` in Nautilus without patches |
| M6 — Temporary window | A snapshot slider, a preview and restoring | The whole time travel flow and restoring |
| M7 — Polish | i18n, a11y, documentation, packaging (distribution and a Flatpak evaluation) | The 1.0 release |

## 11. Decisions

**Adopted:**
1. **Name:** Delta. Namespaces: the D-Bus bus and interface `io.github.sincorchetes.Delta.Service1`, the GSettings schema
   `io.github.sincorchetes.Delta`, the URI `delta://`, the binaries `delta-*`, the Python package `delta`.
2. **The time view in Nautilus:** a GVfs backend and a GTK4 temporary window (see §7), with no fork or patch of Nautilus.
   *(Later: the GVfs backend was replaced by "Browse as a folder"; see `roadmap.md`, M5.)*
3. **A single language:** Python 3 and PyGObject in the whole project.
4. **License:** GPL-3.0-or-later, the standard in the GNOME ecosystem (fixed during M7).
5. **Distribution:** native packages first (rpm, deb, AUR, a Nix flake) and a Flatpak with the window only as the secondary
   target. The first goes with the folder view (`borg mount`); the Flatpak does not mount anything.

**Open:** none at the moment. Pending decisions are in `TODO.md`.

## 12. Performance and access to the backups (2026-11-12)

Today every read query (`ListVersions`, `ListFolder`, `SearchFolder`, `ListDeleted`, `ListChanged`) runs `borg list`, and Borg
has to read the backup's metadata. The versions of a file cost **one call per backup** (with the default GFS retention, up to
about 47). That is the real performance limit; the rest (comparing with the disk by `lstat`) is cheap.

**Done: an in-memory cache of listings** (`infrastructure/listing_cache.py`). A backup **never changes**, so what `borg list`
said holds until it is pruned: there is nothing to invalidate. Besides, listing a folder lists everything below it, so a folder
*inside* one already listed is taken from that listing without asking Borg again. Memory only, bounded (96 MB, LRU). Measure
with `scripts/bench_dbus.py` (run it twice).

**Next, only if the figures ask for it: a persistent index** (SQLite, the standard library's `sqlite3`). The design:
- An **interval** model, not one row per (backup, file): `(path, size, mtime, from, to)` with `from`/`to` being backup sequence
  numbers. A new backup is compared with the previous one and only adds what changed or extends the interval. The size grows with
  the distinct versions, not with backups × files.
- `ListVersions` becomes **a single query**; a folder is a range by path prefix; the search by name uses an indexed column (or
  FTS5).
- It is a **decorator of the `VersionSource` port** (`IndexedVersionSource`): the application and the interface do not change. If
  a backup is not indexed yet, it delegates to Borg (it never gives an incomplete answer). It is built in the background after
  each backup (only the new one) and is **rebuildable**: it is a cache, not the source of truth.
- Pruning a backup does not break the intervals (they are measured by sequence); a sweep deletes the orphans.
- **The privacy cost:** it stores names, sizes and dates in the clear, also for files already deleted. The Borg repository is
  encrypted; the index is not (SQLCipher is not in the standard library). It would have to be documented in `security.md` and
  stored with 0600 permissions in `XDG_CACHE_HOME`, or encrypted with a key from the keyring.
- **A graph is not needed**: what is queried is a tree with versions, and a table ordered by path with intervals already walks
  folders by prefix.

**On GVfs and `ctypes`.** It does not work. A GVfs backend is not a library that gets called: it is a daemon that **implements**
a subclass of `GVfsBackend` (dozens of virtual methods) against `libgvfsdaemon`, an internal API with no GIR and no stable ABI
outside GVfs's tree. With `ctypes` the structures and method tables would have to be replicated by hand, and it would break with
every version. The reasonable alternative for "exploring the backups in Files" is a **FUSE file system in Python** (`pyfuse3`,
already in Nix's Borg) over the index: it reads the metadata from the index (without `borg mount`, so it **does not block the
backups**) and extracts the content of a file only when it is opened. It would replace the original M5 (see `roadmap.md`) and
depends on the index existing.

### Measurement results (2026-11-12, 26 backups)

With the listings cache, the cache of the list of backups and `ListVersions` in parallel (4 Borg at a time): single queries
0.5 s → 0.01 s; `ListVersions` 7 s → 1.98 s cold and 0.07 s warm. The persistent index (SQLite) and the FUSE in Python are
deferred until there are many more backups and the first cold query becomes a problem again.
