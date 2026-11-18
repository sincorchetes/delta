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
#            and without the packages that are built from source
#   then:    setuptools, setuptools-scm and wheel, which a new virtualenv does not come with
#            (without setuptools-scm, python-dbusmock gets the version 0.0.0 and uv rejects it)
#   phase 2: pycairo, python-dbusmock and the project itself
#   phase 3: PyGObject and dbus-python
#
# Everything is built without build isolation, so every build backend must
# already be in the virtualenv: poetry-core for the project, setuptools for
# python-dbusmock. On a machine that already had them, or whose uv cache holds
# the built packages, this does not show; in a fresh environment it does.
#
# "--inexact" keeps what is not in the lock file: by default uv sync removes it,
# and it would remove setuptools just before python-dbusmock needs it.
#
# devenv points UV_PROJECT_ENVIRONMENT at .devenv/state/venv; outside
# devenv the project venv is ./.venv.
set -e

VENV="${UV_PROJECT_ENVIRONMENT:-$PWD/.venv}"
export PATH="$VENV/bin:$PATH"

uv sync --extra dev --inexact --no-install-project \
  --no-install-package pygobject \
  --no-install-package pycairo \
  --no-install-package dbus-python \
  --no-install-package python-dbusmock

uv pip install --python "$VENV/bin/python" setuptools setuptools-scm wheel

uv sync --extra dev --inexact \
  --no-install-package pygobject \
  --no-install-package dbus-python

uv sync --extra dev --inexact
