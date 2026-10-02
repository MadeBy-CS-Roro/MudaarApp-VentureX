#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Install merged dependency changes without prompting or changing the database.
# The merge runner does not inherit Replit's interactive pip target settings.
# Keep packages in the project, not Nix's immutable system Python.
python_version="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
package_dir="$PWD/.pythonlibs/lib/python${python_version}/site-packages"
export PYTHONPATH="${package_dir}${PYTHONPATH:+:${PYTHONPATH}}"
python -m pip install --target "$package_dir" --upgrade --no-input --disable-pip-version-check -r requirements.txt

# Tests use temporary databases, never the running demo database.
python -m pytest -q