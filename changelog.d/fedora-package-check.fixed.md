- **The check of a published package on Fedora no longer waits for a version it already has.** `dnf install` of a package that is
  installed does nothing in DNF 5, so after the first try it never took the newer version that the Build Service published, and the
  job failed after 180 minutes although the package was there (a fault of the check, not of the package).
