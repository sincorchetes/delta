- **A test that reads the repository must be ignored by the mutation tests, and a test now checks it.** One that was not failed only in
  the CI, 12 minutes into the job; now it fails in the suite, saying what to add to `[tool.mutmut]`.
