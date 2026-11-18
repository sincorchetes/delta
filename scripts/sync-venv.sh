#!/bin/sh
# Three-phase uv sync.
#
# PyGObject, pycairo and dbus-python ship as meson-based source
# distributions and are built without build isolation ([tool.uv]
# no-build-isolation), so the meson/ninja toolchain must already live in
# the virtualenv when they compile. pycairo must additionally be present
# before PyGObject builds (its cairo extension includes <py3cairo.h>).
#
#   phase 1: the build tools (meson-python, poetry-core...), without the project
#   phase 2: pycairo, and the project itself
#   phase 3: PyGObject and dbus-python
#
# The project is built without build isolation too, so its build backend
# (poetry-core) must already be in the virtualenv: that is why phase 1 does not
# install it ("--no-install-project"). In an environment that already had it
# from an earlier run this does not show; in a fresh one it does.
#
# devenv points UV_PROJECT_ENVIRONMENT at .devenv/state/venv; outside
# devenv the project venv is ./.venv.
set -e

VENV="${UV_PROJECT_ENVIRONMENT:-$PWD/.venv}"
export PATH="$VENV/bin:$PATH"

uv sync --extra dev --no-install-project \
  --no-install-package pygobject \
  --no-install-package pycairo \
  --no-install-package dbus-python

uv sync --extra dev \
  --no-install-package pygobject \
  --no-install-package dbus-python

uv sync --extra dev
