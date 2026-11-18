# Delta on the openSUSE Build Service

OBS builds the packages and publishes a repository for each distribution. The project is
[`home:sincorchetes:delta`](https://build.opensuse.org/project/show/home:sincorchetes:delta).

## The repositories

| Repository | Builds against | Architectures | For |
|---|---|---|---|
| `Fedora_43`, `Fedora_44` | `Fedora:43/standard`, `Fedora:44/standard` | `x86_64`, `aarch64` | Fedora |
| `openSUSE_Tumbleweed` | `openSUSE:Factory/snapshot` | `x86_64`, `aarch64` | openSUSE Tumbleweed |
| `RockyLinux_10` | `RockyLinux:10/baseos`, `appstream`, `CRB`, then `Fedora:EPEL:10/standard` | `x86_64` | Rocky Linux 10 |
| `AlmaLinux_10` | `AlmaLinux:10/baseos`, `appstream`, `CRB`, then `Fedora:EPEL:10/standard` | `x86_64`, `aarch64` | AlmaLinux 10 |
| `Debian_13` | Debian 13 (from the list of distributions) | `x86_64` | Debian 13 |
| `xUbuntu_26.04`, `xUbuntu_26.10` | Ubuntu 26.04 and 26.10 (from the list of distributions) | `x86_64` | Ubuntu 26.04 and 26.10 |

Ubuntu 24.04 was built too, but its repository never got published, so it was left out: whoever needs it builds the package.

The package is pure Python, so the build is the same everywhere.

Rocky and AlmaLinux are binary compatible, but each one has a repository of its own, so that each is built and tried on its
own environment instead of assuming that they are the same.

The two need the extra paths. `RockyLinux:10/standard` and `AlmaLinux:10/standard` do not hold the base system (`rpm` is in
`baseos`), `meson` and the `-devel` packages are in CRB, and `appstream` (used by `meson test`) is in EPEL. At install time,
`borgbackup` also comes from EPEL, so users of Rocky and AlmaLinux must enable it first.

Rocky has no `aarch64`: OBS mirrors only 147 packages of its `baseos` for ARM (AlmaLinux has 954), and `rpm` is not among
them, so the repository cannot be set up. Whoever needs Rocky on ARM can build the package.

Arch is not built here: it goes to the AUR, from `packaging/arch/PKGBUILD`.

## Publishing a version

The package is `delta-backup`. Its files are:

- `packaging/rpm/delta-backup.spec` for the RPM repositories;
- `packaging/obs/delta-backup.dsc` and a `debian.tar.gz` with the `debian/` directory, for Debian and Ubuntu;
- `packaging/obs/_service`, which downloads the source from the tag `vX.Y.Z` on GitHub, so **the tag must exist first**.

The source is the same tarball for all of them. In the `.dsc`, `DEBTRANSFORM-TAR` names it and `DEBTRANSFORM-FILES-TAR` names
the tarball of `debian/`: OBS makes the Debian source package from them. The tarball of `debian/` leaves out `debian/source`,
because the source package that OBS makes this way is in format 1.0.

```sh
git clone --depth 1 --branch vX.Y.Z https://github.com/sincorchetes/delta.git source
osc checkout home:sincorchetes:delta delta-backup      # the package that already exists in OBS
cd home:sincorchetes:delta/delta-backup
cp ../../source/packaging/rpm/delta-backup.spec ../../source/packaging/obs/_service ../../source/packaging/obs/delta-backup.dsc .
tar --owner=0 --group=0 --exclude=debian/source -czf debian.tar.gz -C ../../source debian
osc status                             # the four files, with M
osc commit -m "Delta X.Y.Z"
```

Do not use `osc mkpac` or `osc add` for an update: they make a new local package, and `osc commit` then fails with `package
'delta-backup' already exists`. (`mkpac` and `add` are only for creating the package the first time.)

If the tarball does not show up after the commit, run `osc service remoterun`. To follow the builds:

```sh
osc results                            # one line for each repository and architecture
osc results -v                         # the reason of each failure
osc buildlog Fedora_44 x86_64          # the log of one build
```

A new release changes the version in `delta-backup.spec`, in `delta-backup.dsc` (the version and the name of the tarball) and
in the path of `_service` (all of them are in the list of files `CONTRIBUTING.md` asks to update), and is published with the
same commands.

## Check what was published

Install the package in a clean container, from the repository OBS publishes, and see that it imports. For Rocky; for
AlmaLinux use `docker.io/library/almalinux:10` and `AlmaLinux_10`:

```sh
podman run --rm quay.io/rockylinux/rockylinux:10 sh -c '
  dnf install -y epel-release &&
  dnf config-manager --add-repo https://download.opensuse.org/repositories/home:/sincorchetes:/delta/RockyLinux_10/home:sincorchetes:delta.repo &&
  dnf install -y delta-backup &&
  python3 -c "import gi; gi.require_version(\"Adw\",\"1\"); from delta.ui import application; print(\"imports ok\")"'
```

The repository URLs follow the pattern `https://download.opensuse.org/repositories/home:/sincorchetes:/delta/<repository>/`.
Fedora 44, openSUSE Tumbleweed, Rocky 10 and AlmaLinux 10 were checked this way.
