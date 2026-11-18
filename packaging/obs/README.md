# Delta on the openSUSE Build Service

OBS builds the RPM packages and publishes a repository for each distribution. The project is
[`home:sincorchetes:delta`](https://build.opensuse.org/project/show/home:sincorchetes:delta).

## The repositories

| Repository | Builds against | For |
|---|---|---|
| `Fedora_43`, `Fedora_44` | `Fedora:43/standard`, `Fedora:44/standard` | Fedora |
| `openSUSE_Tumbleweed` | `openSUSE:Factory/snapshot` | openSUSE Tumbleweed |
| `RockyLinux_10` | `RockyLinux:10/standard`, then `RockyLinux:10/CRB`, then `Fedora:EPEL:10/standard` | Rocky Linux 10 |
| `AlmaLinux_10` | `AlmaLinux:10/standard`, then `AlmaLinux:10/CRB`, then `Fedora:EPEL:10/standard` | AlmaLinux 10 |

All of them build `x86_64` and `aarch64`. The package is pure Python, so the build is the same everywhere.

Rocky and AlmaLinux are binary compatible, but each one has a repository of its own, so that each is built and tried on its
own environment instead of assuming that they are the same.

The two need the extra paths: `meson` and the `-devel` packages are in CRB, and `appstream` (used by `meson test`) is in EPEL.
At install time, `borgbackup` also comes from EPEL, so users of Rocky and AlmaLinux must enable it first.

Debian and Ubuntu are not set up yet: they need the `debian/` files packaged for OBS (a second phase).

Arch is not built here: it goes to the AUR, from `packaging/arch/PKGBUILD`.

## Publishing a version

The package is `delta-backup`. Its files are `packaging/rpm/delta-backup.spec` and `packaging/obs/_service`; the service
downloads the source from the tag `vX.Y.Z` on GitHub, so **the tag must exist first**.

```sh
osc checkout home:sincorchetes:delta
cd home:sincorchetes:delta
osc mkpac delta-backup                 # only the first time
cd delta-backup
cp <repo>/packaging/rpm/delta-backup.spec <repo>/packaging/obs/_service .
osc add delta-backup.spec _service     # only the first time
osc commit -m "Delta X.Y.Z"
```

If the tarball does not show up after the commit, run `osc service remoterun`. To follow the builds:

```sh
osc results                            # one line for each repository and architecture
osc buildlog Fedora_44 x86_64          # the log of one build
```

A new release changes the version in `delta-backup.spec` and in the path of `_service` (both are in the list of files
`CONTRIBUTING.md` asks to update), and is published with the same commands.

## Check what was published

Install the package in a clean container, from the repository OBS publishes, and see that it imports. For Rocky; for
AlmaLinux use `almalinux:10` and `AlmaLinux_10`:

```sh
podman run --rm quay.io/rockylinux/rockylinux:10 sh -c '
  dnf install -y epel-release &&
  dnf config-manager --add-repo https://download.opensuse.org/repositories/home:/sincorchetes:/delta/RockyLinux_10/home:sincorchetes:delta.repo &&
  dnf install -y delta-backup &&
  python3 -c "import gi; gi.require_version(\"Adw\",\"1\"); from delta.ui import application; print(\"imports ok\")"'
```

The repository URLs follow the pattern `https://download.opensuse.org/repositories/home:/sincorchetes:/delta/<repository>/`.
