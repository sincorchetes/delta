#!/bin/sh
# Three-phase uv sync.
#
# PyGObject, pycairo and dbus-python ship as meson-based source
# distributions and are built without build isolation ([tool.uv]
# no-build-isolation), so the meson/ninja toolchain must already live in
# the virtualenv when they compile. pycairo must additionally be present
# before PyGObject builds (its cairo extension includes <py3cairo.h>).
#
#   phase 1: everything except the GNOME sdists (gets meson-python etc.)
#   phase 2: pycairo
#   phase 3: PyGObject and dbus-python
#
# devenv points UV_PROJECT_ENVIRONMENT at .devenv/state/venv; outside
# devenv the project venv is ./.venv.
set -e

VENV="${UV_PROJECT_ENVIRONMENT:-$PWD/.venv}"
export PATH="$VENV/bin:$PATH"

uv sync --extra dev \
  --no-install-package pygobject \
  --no-install-package pycairo \
  --no-install-package dbus-python

uv sync --extra dev \
  --no-install-package pygobject \
  --no-install-package dbus-python

uv sync --extra dev
