# Delta D-Bus API

The session bus · the name `io.github.sincorchetes.Delta.Service1` · the object `/io/github/sincorchetes/Delta/Service1` · the
interface `io.github.sincorchetes.Delta.Service1`. The source of truth is `src/delta/daemon/introspection.py`; this document
explains the semantics.

The daemon is activated by itself on first use (`SystemdService=delta.service`).

## Job model

Long operations return a `job_id` at once and end with a signal. **There is only one job at a time**: a second request gets
`Busy`. A job emits zero or more `Progress` signals and exactly one `BackupFinished` (the name is historical: it is emitted for
*every* kind of job, not just backups).

## Methods

| Method | Input | Output | Notes |
|---|---|---|---|
| `CreateBackup` | – | `job_id` s | Backs up the folders in `backup-sources` (empty = `$HOME`). With Borg warnings it ends with `ok=true` and the text in `message`. |
| `CreateRepository` | `location` s, `passphrase` s | `job_id` s | An empty `passphrase`: the daemon generates a 256-bit one and stores it in the keyring; it never leaves the daemon. It creates the parent directories of a local repository (0700). It saves `repository-location` when it ends well. |
| `UnlockRepository` | – | `job_id` s | Runs `borg break-lock` on the configured repository and, if it goes well, forgets the last error. **Only on an explicit, confirmed request from the user**: breaking a lock that really is in use can damage the backups. Like any job, it answers `Busy` if another is running, so it never unlocks under a backup of the daemon's own. |
| `UseRepository` | `location` s, `passphrase` s | `job_id` s | Adopts a repository that **already exists** (a reinstall, another computer). It requires the passphrase, checks that it opens the repository (`borg list`) and only then stores it in the keyring and sets `repository-location`. It never runs `borg init`; if it does not open, it leaves the keyring as it was. |
| `ListSnapshots` | – | `aa{sv}` | Keys: `id` s, `name` s, `time` x (epoch). Most recent first. It excludes Borg's `.checkpoint` files (partial backups). |
| `ListVersions` | `path` s | `aa{sv}` | The distinct versions of the file across the snapshots (identical ones collapse), most recent first. Keys: `id`, `name`, `time`, `size` x, `mtime` x. |
| `ListFolder` | `snapshot_id` s, `path` s | `aa{sv}` | What a folder contained in a snapshot, **one level** (nothing is extracted). Keys: `name`, `is_dir` b, `size` x (a subfolder adds up its content), `mtime` x. `ListVersions` also adds `is_dir`. Errors: `InvalidPath`, `Failed` (a nonexistent snapshot). |
| `SearchFolder` | `snapshot_id` s, `path` s, `query` s | `aa{sv}` | Entries **at any depth** under a folder, in a snapshot, whose own name contains `query` (case-insensitive), at most 1000. The same keys as `ListFolder`, with `name` = the path **relative** to the folder; the `size` of a folder is 0. An empty query: an empty list. Errors: `InvalidPath`, `Failed`. |
| `ListDeleted` | `snapshot_id` s, `folder` s | `aa{sv}` | What `folder` contained in that snapshot and **no longer exists on the disk**: a deleted folder is **one** item (its `size` adds up everything inside) and what was inside it is not repeated. Something that exists today with the same name does not count as deleted, not even if it is now of another kind, nor if the disk cannot be queried. Keys as `ListFolder`; `name` relative to `folder`. Errors: `InvalidPath`, `Failed`. |
| `ListChanged` | `snapshot_id` s, `folder` s | `aa{sv}` | `ListDeleted` **plus** every file, at any depth, whose size or date differs today from what the backup had (or that is now a folder). It compares **file by file**, not by folder totals. Symbolic links and what cannot be read are not judged. The same keys; `name` relative to `folder`, sorted by name. |
| `RestoreDeleted` | `snapshot_id` s, `folder` s | `job_id` s | Puts back **everything in `ListDeleted`**, under its original name, in **a single job**: it extracts it together (500 paths per call to Borg) and puts it back. The set is **recomputed** when it runs; it does not trust an earlier query. It overwrites nothing: what already exists is left alone. It recreates the folders that are missing, only inside `$HOME`. The `message` of `BackupFinished` = the number of items restored, in decimal. |
| `Restore` | `snapshot_id` s, `source_path` s, `target_path` s | `job_id` s | Extracts under an existing directory of `$HOME`, recreating the original path inside. |
| `RestoreAsCopy` | `snapshot_id` s, `path` s | `job_id` s | Leaves the old version **next to the original**: `name (restored YYYY-MM-DD).ext`. It overwrites nothing. The `message` of `BackupFinished` = the path created. |
| `RestoreReplace` | `snapshot_id` s, `path` s | `job_id` s | Puts the old version in the place of the original, **first setting the current one aside** as `name (before restoring YYYY-MM-DD HH-MM-SS).ext`. If it fails, it puts the original back. `message` = the restored path. |
| `PreviewVersion` | `snapshot_id` s, `path` s | `job_id` s | Unpacks the version (a file or a folder) **read-only** under `$XDG_RUNTIME_DIR/delta/preview/` (in a Flatpak, under the application's cache folder, `$XDG_CACHE_HOME/delta/preview/`), to see it without restoring. The `message` of `BackupFinished` = the unpacked path. It is a job: it answers `Busy` if another is running. |
| `ClearPreviews` | – | – | Forgets every preview. The daemon also deletes them when it starts and when it stops. |
| `MountSnapshot` | `snapshot_id` s | `job_id` s | Opens the backup as a read-only folder (`borg mount`) under `$XDG_RUNTIME_DIR/delta/browse/`. The `message` of `BackupFinished` = the folder. If a backup is running, it **interrupts** it (it resumes by itself when the folder is closed) and waits for it to release the repository (up to about 5 s). Only one is open: opening another closes the previous. The daemon watches the client that asked for it and closes it if it disappears. `Unavailable` if there is no mounting (a Flatpak). |
| `UnmountSnapshot` | – | `job_id` s | Closes the open backup (`""` if there was none) and restarts the interrupted or postponed backup. |

`snapshot_id` accepts either the id or the name of the snapshot.

## Signals

- `Progress(job_id s, percent d, path s)`: `percent = -1.0` means indeterminate (Borg gives no reliable total). `path` is the
  file in progress.
- `BackupFinished(job_id s, ok b, message s)`:
  - `ok=false`: `message` is the reason (technical text, translatable).
  - `ok=true` and an empty `message`: success.
  - `ok=true` and a non-empty `message`: success with a warning (a backup made with Borg warnings, or a failed prune), or the
    resulting path in `RestoreAsCopy/Replace` and `PreviewVersion`.
  - A backup interrupted (a shutdown, a restart) ends with `ok=false` and is **resumed by itself** when the daemon starts again.

- `SnapshotClosed(reason s)`: the daemon closed the open backup; the window that was showing it must close. `reason`: `requested`,
  `owner-gone`, `sleep-or-lock` (suspending or locking the session), `shutdown`, `repository-changed` or `unused` (2 minutes
  without any program having a file, working directory or window in it; it is checked every 30 s by reading `/proc`, ignoring the
  `gvfsd*` processes, which always watch the root of every mount. A long copy keeps its file open, so it is not cut off). While a
  backup is open, `CreateBackup` answers `Busy` and the backup is postponed: it is made when the folder is closed.

## Properties (read-only)

- `CanMount` b: whether this installation can open backups as a folder (false in a Flatpak); the UI hides "Browse as a folder"
  when it is false.
- `Status` s: `idle` | `running` | `browsing` | `unavailable`. `unavailable` is that the latest backup found the place of the
  repository unreachable (a drive that is not connected, a folder that is gone, the empty mount point of a drive that is not
  mounted): it is not a failure, `LastError` stays empty, and it ends with the next backup, which runs by itself when the place is
  back. A backup that is `running` is `running` whatever the previous one found.
- `LastBackup` t: the epoch of the last successful backup (0 = none). When the daemon starts, it takes it from the most recent
  snapshot of the repository.
- `NextBackup` t: the epoch of the next scheduled backup (0 = unknown or not scheduled). It is read from the scheduler's timer and
  cached for up to 60 s; the first read after starting can return 0.
- `LastError` s: the reason for the failure of the last *backup* (empty if the last one went well; restores do not change it). An
  interrupted backup leaves "interrupted; it will be resumed" here until the next one finishes.

## Errors

They are returned as D-Bus errors `io.github.sincorchetes.Delta.Service1.Error.*`:

| Error | When |
|---|---|
| `Busy` | A job is already running. |
| `InvalidPath` | A relative path, one with `..`, outside `$HOME`, or whose resolved directory (symlinks) escapes `$HOME`. |
| `InvalidArgument` | An empty `location` in `CreateRepository`, or no valid source in `CreateBackup`. |
| `Unavailable` | The service that is needed is not wired. |
| `Failed` | An error when querying (asynchronous reads). |

A failure *inside* a job that was already accepted is not a D-Bus error: it arrives in `BackupFinished(ok=false)`.

## Related configuration (GSettings `io.github.sincorchetes.Delta`)

`repository-location` (s) · `backup-sources` (as, empty = `$HOME`) · `excluded-paths` (as, absolute paths that are skipped with
all their content; the daemon passes them to Borg as `pp:<path>`, a literal prefix with no wildcards, in addition to the cache
and the trash, which are always skipped) · `schedule` (s, an `OnCalendar` expression) · `keep-hourly|daily|weekly|monthly` (i).
The daemon reloads these values when they change, but **never interrupts a running job**: it waits for it to finish.
