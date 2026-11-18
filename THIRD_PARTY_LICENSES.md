# Third-party software and licenses

Delta is © 2026 Álvaro Castillo (<https://sincorchetes.tech>) and co-authored with Claude (Anthropic),
under the **GNU General Public License, version 3 or later** (`GPL-3.0-or-later`; the text is in
[`LICENSE`](LICENSE)).

Delta uses, and was built and tested with, the free software below. Each project keeps its own
license and copyright. The licenses are the ones each project declares; they are written down here as
of November 2026 and should be checked again before every release. The «Source» column says where
each one was read from: **metadata** (the package's own record in the project's environment) or
**documentation** (the project's published license, not re-read from a file in this repository).

## What Delta uses while it runs

These are also listed in the application, under *About Delta → Legal*.

| Component | License | Source |
|---|---|---|
| GTK 4 | LGPL-2.1-or-later | documentation |
| libadwaita | LGPL-2.1-or-later | documentation |
| GLib and GIO | LGPL-2.1-or-later | documentation |
| GStreamer | LGPL-2.1-or-later | documentation |
| libsecret | LGPL-2.1-or-later | documentation |
| systemd | LGPL-2.1-or-later | documentation |
| PyGObject | LGPL-2.1-or-later | metadata («GNU Lesser General Public License») |
| pycairo | LGPL-2.1-only OR MPL-1.1 | metadata |
| Python | PSF-2.0 | documentation |
| BorgBackup | BSD-3-Clause | documentation |
| nautilus-python | GPL-2.0-or-later | documentation |

## What the code was tested and built with

| Component | License | Source |
|---|---|---|
| pytest | MIT | metadata |
| pytest-cov | MIT | metadata |
| coverage | Apache-2.0 | metadata |
| python-dbusmock | LGPL (version as declared by the project) | metadata |
| mutmut | BSD-3-Clause | metadata |
| dbus-python | MIT AND (GPL-2.0-or-later OR AFL-2.1) | metadata |
| Meson | Apache-2.0 | metadata |
| meson-python | MIT | metadata |
| poetry-core | MIT | metadata |
| uv | MIT OR Apache-2.0 | documentation |
| ruff | MIT | documentation |
| Nix | LGPL-2.1-or-later | documentation |
| devenv | Apache-2.0 | documentation |

## What the documentation site is built with

| Component | License | Source |
|---|---|---|
| Astro | MIT | metadata |
| Starlight (`@astrojs/starlight`) | MIT | metadata |
| `@astrojs/check` | MIT | metadata |
| TypeScript | Apache-2.0 | metadata |
| Bun | MIT (it bundles JavaScriptCore, under LGPL-2.0) | documentation |

## Authorship

Delta was written by Álvaro Castillo, with Claude (Anthropic) as co-author: the assistant wrote and
reviewed code, tests and documentation in a working session with the author, who decided what to
build and checked it on a real desktop.
