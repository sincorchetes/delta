- **A pull request that changes nothing the mutation tests read skips them.** They were 511 of the 780 seconds of the `devenv` job,
  even for a change to `TODO.md`. They run when `src/`, `tests/`, `po/` or their configuration change (and for anything not known to
  be safe), and on every push to `main`.
