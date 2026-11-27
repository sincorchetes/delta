# Changelog fragments

Each pull request that a person would notice adds **one file here** instead of editing `CHANGELOG.md`, so two pull requests never
conflict over the same lines.

- Name: `<what-it-is-about>.<kind>.md`, where kind is `added`, `changed`, `deprecated`, `removed`, `fixed` or `security`
  (the headings of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)).
- Content: one entry, as it will be read in the changelog: a bullet that starts with `- **A bold sentence.**` and goes on, its
  lines indented by two spaces.

The pull request that raises the version runs `sh scripts/ci/changelog_assemble.sh X.Y.Z` (it sets today's date, or give
`YYYY-MM-DD` as a third argument): the entries go to a new section of `CHANGELOG.md` and the fragments are deleted.
