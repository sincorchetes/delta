# Contributing to Delta

Thank you for helping. This page is the short version; [`AGENTS.md`](AGENTS.md) is the complete one and has the
architecture rules, the development environment and what "done" means.

## How a change gets in

`main` is the stable branch and nobody pushes to it. Every change follows the same path:

1. Create a **new branch** from `main`: `feature/…`, `fix/…` or `docs/…`.
2. Open a **pull request**. The template lists what to check.
3. The **CI must be green**: the tests, the mutation tests and the website build. The check on each distribution's own libraries is
   a separate workflow that does not block a pull request.
4. It is merged by **squash**, and the branch is deleted.

## Set up

Delta uses [devenv](https://devenv.sh/) for the system libraries and [uv](https://docs.astral.sh/uv/) for the Python packages.

```sh
devenv shell
sync     # install the Python packages
build    # configure and compile with Meson
test     # run the tests
cov      # run the tests with coverage
```

The widget tests need a display. Where there is none, run them under a virtual one: `xvfb-run -a uv run pytest`. They never show a window.

## Before you push

**Run all the tests before any push**, not only those of what you changed: a push is not a way to let the CI try it. If something
fails here, it is fixed here.

```sh
xvfb-run -a uv run pytest --cov     # must stay at 100 % of lines and branches
sh scripts/ci/check_mutants.sh      # mutation tests: at most the one known equivalent survivor
meson setup build && meson test -C build
ruff check src tests scripts
```

## What a change needs

- **Tests.** Every change comes with them. **Coverage is 100 % of lines and branches** and there is no `# pragma: no cover`:
  if something cannot be tested, simplify the code. Unit tests for the domain and application layers, and an integration test
  (a real Borg in a temporary folder, a fake D-Bus) where it applies.
- **Mutation tests.** If you touch the domain, the application layer, the Borg commands or their parsing, run them. A mutant that
  survives means a test does not really watch the code: strengthen the test, or simplify the code.
- **Architecture.** Four layers: `domain` (pure) → `application` → `infrastructure` → `daemon`/`ui`/`nautilus`. Dependencies point inward.
  A file has about 300 lines at most and one responsibility.
- **Translations.** Every visible string goes through `delta.i18n._()` or `ngettext()`. List the file in `po/POTFILES.in` and
  translate the new strings in `po/es.po`. Code and identifiers are in English.
- **Documentation.** If behavior changes, update the website (`website/src/content/docs/`, in English and Spanish), the in-app help
  (`help/`), and `docs/` where it applies. Keep `TODO.md` and `docs/ROADMAP.md` up to date.
- **Flatpak.** Nothing from the host (paths, binaries, `secret-tool`) outside its adapter. The window and the Files extension only
  talk to the daemon over D-Bus.

## A new version

A release is one more pull request. It changes the version in `meson.build`, `packaging/rpm/delta-backup.spec` (and its
`%changelog`), `debian/changelog`, `packaging/arch/PKGBUILD`, `packaging/obs/delta-backup.dsc` and `CHANGELOG.md`, and sets the date of the
release in the changelog. `tests/unit/test_packaging.py` fails if they disagree. Once it is merged, tag `main` as `vX.Y.Z`
(for example `v0.1.0`, with no dot after the `v`).

Pushing the tag does most of the rest:

- `flatpak.yml` builds the Flatpak, makes the GitHub Release with the notes of that version in `CHANGELOG.md`, and attaches the
  bundle.
- `release.yml` publishes the package to the AUR: the real checksum of the tarball of the tag (the `PKGBUILD` keeps `SKIP`, since
  the sum only exists once the tag does) and `.SRCINFO`. Run it by hand (*Actions → Publish packages → Run workflow*) with a tag
  and *dry run* on to check a publication without pushing anything.
- `release.yml` also publishes to the openSUSE Build Service: it moves the branch `release` to the tag and asks OBS to run its
  source service, which fetches the spec, the `.dsc`, `debian/` and the tarball of that branch by itself. Nothing is uploaded to
  OBS by hand; how the project is set up is in `packaging/obs/README.md`.

### What the maintainer sets up once

The credentials are in a GitHub environment named `release` (*Settings → Environments*), limited to `main` and the tags `v*`:

| Name | Kind | What |
|---|---|---|
| `AUR_SSH_PRIVATE_KEY` | secret | A key made only for this, whose public half is in the AUR account. |
| `AUR_GIT_NAME`, `AUR_GIT_EMAIL` | variables | The author of the commits in the AUR. |
| `OBS_TOKEN` | secret | An OBS token of type `service`, bound to the package `delta-backup` (it can only run its source service). Without it OBS is not published. |

The host keys of the AUR are in `scripts/ci/aur_known_hosts` (taken with `ssh-keyscan aur.archlinux.org`; the Arch wiki does not
publish their fingerprints), so the workflow never trusts a key it was not given. If the AUR ever changes its keys, the push fails
on purpose: take them again, check them from a network that is not yours, and commit the file.

## Reporting problems

- A bug or an idea: open an issue and fill in the form.
- A security problem: **do not** open an issue. Read [`SECURITY.md`](SECURITY.md).

By contributing you agree that your work is released under the project's license, GPL-3.0-or-later.
