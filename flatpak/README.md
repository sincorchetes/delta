# Delta as a Flatpak

The Flatpak has the window: previous versions, preview, restore, status, history and preferences. It does
not have **Browse as a folder** (a FUSE mount inside the sandbox is not seen by the file manager) nor the
**Nautilus extension** (Nautilus runs outside the sandbox and loads its extensions from the computer). Backups
are scheduled by the daemon itself, with its own clock, because there is no `systemd --user` in a sandbox;
the Background portal lets it keep running and start at login.

## Build and try it

In `devenv shell` (it brings `flatpak-builder` and a `flatpak` enough for `--user` installs; to run the result
integrated in your session, with portals and the background start, also set `services.flatpak.enable = true;`
on NixOS):

```sh
flatpak-build                       # adds Flathub for your user, fetches the runtime and builds + installs
flatpak run io.github.sincorchetes.Delta
```

Without devenv, the same by hand:

```sh
flatpak install flathub org.gnome.Platform//50 org.gnome.Sdk//50
flatpak-builder --user --install --force-clean build-flatpak flatpak/io.github.sincorchetes.Delta.yaml
```

On NixOS add `--disable-rofiles-fuse` (`flatpak-build` does): `rofiles-fuse` needs a setuid `fusermount`, and the
one of the Nix store is not.

The runtime (`50`) is the one the manifest names: use the current stable GNOME runtime when publishing.

## For Flathub

- **Two manifests.** `io.github.sincorchetes.Delta.yaml` builds your working copy (`type: dir`) to try changes;
  `io.github.sincorchetes.Delta.flathub.yaml` builds the tag of a release (`type: git`, with its commit) and is the one
  submitted to Flathub, as `io.github.sincorchetes.Delta.yaml` next to `python3-borgbackup.json`. A new version changes the
  `tag` and the `commit` there, and the release in the metainfo.
- **Offline sources.** `python3-borgbackup.json` was made with
  [flatpak-pip-generator](https://github.com/flatpak/flatpak-builder-tools/tree/master/pip)
  (`--output python3-borgbackup pkgconfig setuptools-scm borgbackup`): pinned sources and hashes, no network. The
  OpenSSL, lz4 and zstd that BorgBackup builds against come from the SDK. Regenerate it when BorgBackup changes.
- **Checks.** `flatpak run --command=flatpak-builder-lint org.flatpak.Builder manifest <manifest>` and `... repo <repo>`.
  On a local build the repository check reports the screenshots as not mirrored: Flathub mirrors them itself.
- **Permissions.** `--filesystem=home` is wide, because a backup program has to read what it backs up and
  write what it restores. Flathub will ask why: the answer is this paragraph.

## Right-click in Files

Files loads its extensions from the computer, never from a Flatpak, so the Flatpak cannot add **Restore
Previous Version…** by itself. The extension (`src/nautilus/delta_extension.py`) needs nothing of Delta: it
opens the app through the exported `io.github.sincorchetes.Delta.Versions.desktop` and asks the daemon over D-Bus,
so it works with the Flatpak too. A user installs it by hand next to Files (`nautilus-python` from their
distribution, then the file in `~/.local/share/nautilus-python/extensions/`); the steps are in the website's
install page. Its texts stay in English (the catalogue is inside the sandbox) and the column and emblems read
settings that the sandbox keeps to itself, so they may be less precise than in the native install.

## A Flatpak and a native install in the same session

They share the D-Bus name `io.github.sincorchetes.Delta.Service1`, so whichever daemon starts first answers
both windows, and the Flatpak window would talk to the native daemon and its settings. Install one or the
other. (To try the Flatpak on a machine that has the native one, stop the native daemon first.)

## Where things live in the sandbox

- Settings: GSettings in the app's own data folder (`~/.var/app/io.github.sincorchetes.Delta/`).
- The repository passphrase: the Secret portal (libsecret uses it by itself in a sandbox), under this
  application's own keyring entry. A backup made by the native install and opened from the Flatpak needs
  the recovery key, as in any reinstall.
- D-Bus: the daemon owns `io.github.sincorchetes.Delta.Service1`, a name that starts with the application's
  identifier, so it needs no extra permission.
