# Security policy

## Supported versions

Delta is at its first release. Only the latest release gets security fixes.

| Version | Supported |
|---|---|
| 0.1.x | yes |

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** Use GitHub's private reporting instead:

1. Go to the **Security** tab of this repository.
2. Choose **Report a vulnerability**.
3. Describe what you found, how to reproduce it and what you think the impact is.

Only the maintainer can see the report. If you cannot use that form, open an issue that says only that you need a private
way to report a security problem, with no details, and you will be given one.

You can expect a first reply within 7 days. Delta is maintained by one person, so that is a goal and not a guarantee.
A confirmed problem is fixed in a new release and credited in the changelog, unless you prefer to stay anonymous.

## What counts

Delta stores backups of personal files, so these matter most:

- Reading or writing files outside the places Delta is meant to touch (path validation, restoring outside your home folder).
- A password, a recovery key or any other secret that ends up in a file, a log, a command line or the environment.
- A restore that destroys the files the user already has.
- Another program, or another user, getting Delta to run something it should not.

What Delta does and does not protect against is written down in [`docs/security.md`](docs/security.md), including the
known limits. In particular, **software that already runs as your own user is out of scope**: it can read your keyring,
your session bus and your files whether or not Delta is installed.

## Dependencies

Delta uses [BorgBackup](https://www.borgbackup.org/) for the copies. A problem in Borg itself should be reported to the Borg project.
If Delta uses Borg in a way that makes the problem worse, report that here.
