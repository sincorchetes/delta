- **The tests of the devenv scripts `test` and `cov` run on every core** (`pytest-xdist`): the whole suite goes from about 110 to
  about 40 seconds. `test -n 0` runs it in one process, and the commands of `AGENTS.md` and the CI are unchanged.
