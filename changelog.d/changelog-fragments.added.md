- **Each change writes its entry of the changelog in a file of its own** (`changelog.d/`), not in `CHANGELOG.md`, so two pull
  requests no longer conflict there; the version pull request gathers them with `scripts/ci/changelog_assemble.sh`.
