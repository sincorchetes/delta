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

The package is `delta-backup`, and **OBS fetches its sources from this repository by itself**. Nothing is uploaded to OBS by
hand: the package holds only a source service, `_service` (a copy of it is `packaging/obs/_service`), that reads the branch
`release` of the repository and produces:

- the tarball of the code, `delta-X.Y.Z.tar.gz` (the version comes from the nearest tag, without the `v`);
- `delta-backup.spec`, for the RPM repositories;
- `delta-backup.dsc` and `debian.tar.gz` (the `debian/` directory, without `debian/source`), for Debian and Ubuntu. In the `.dsc`,
  `DEBTRANSFORM-TAR` names the tarball and `DEBTRANSFORM-FILES-TAR` the tarball of `debian/`; OBS makes the Debian source
  package from them, in format 1.0, which is why `debian/source` is left out.

**Pushing a tag `vX.Y.Z` does it.** `.github/workflows/release.yml` moves the branch `release` to the tag and asks OBS to run
the service with a token (the secret `OBS_TOKEN`) that is bound to this package and can do nothing else. OBS then builds every
repository above. The branch `release` is moved only by that workflow; do not work on it.

To try it without touching anything, run the workflow by hand (*Actions → Publish packages → Run workflow*) with *dry run* on.

### How the project is set up

- **Project Config** has one line, `Prefer: wget2-wget`. OBS adds a download service for sources that are URLs, and in Fedora
  `wget` has two candidates (`wget1-wget` and `wget2-wget`) that it cannot choose between: without the line the builds are
  `unresolvable`.
- **The token** is made in OBS (*Your profile → Tokens → Create Token*), of type `service`, for `home:sincorchetes:delta` and
  `delta-backup`. It is shown once: it goes into the secret `OBS_TOKEN` of the `release` environment of GitHub, nowhere else.
- **A new release** changes the version in `delta-backup.spec` and `delta-backup.dsc` (the version and the name of the tarball),
  among the files `CONTRIBUTING.md` asks to update. `_service` does not carry a version.

To follow the builds from a terminal (`osc`):

```sh
osc results home:sincorchetes:delta delta-backup      # one line for each repository and architecture
osc results -v                                        # the reason of each failure
osc buildlog Fedora_44 x86_64                         # the log of one build
```

If something has to be published without the workflow, run the service by hand: `osc service remoterun home:sincorchetes:delta
delta-backup` (after moving the branch `release` to the tag).

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
