## What and why

<!-- What does this change, and why? Link the issue if there is one. -->

## Checklist

- [ ] There are **tests**, and `xvfb-run -a uv run pytest --cov` stays at 100 % of lines and branches.
- [ ] If I touched the domain, the application layer or the Borg commands: `sh scripts/ci/check_mutants.sh` passes.
- [ ] Every new visible string goes through `_()`, is listed in `po/POTFILES.in` and is translated in `po/es.po`.
- [ ] The **documentation** is updated: the website (English and Spanish), the in-app help or `docs/`, where it applies.
- [ ] `TODO.md` and `docs/ROADMAP.md` are up to date.
- [ ] Nothing from the host (paths, binaries) is used outside its adapter, so the Flatpak keeps working.
- [ ] If this is a release: the version is the same in all the places listed in `CONTRIBUTING.md`.

## How I checked it

<!-- The scenario you ran for real (not just the tests): the distribution, native or Flatpak, and what you saw. -->
