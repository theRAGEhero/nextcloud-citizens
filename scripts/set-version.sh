#!/bin/sh
# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
# Single source of truth for the app version.
#
# The App Store matches a release against <version> in appinfo/info.xml, AppAPI
# registers the version it finds there, and the recorder busts its asset cache
# with the version the running app reports — so all of these must agree.
#
# Usage: sh scripts/set-version.sh 0.6.0-beta.1
set -eu

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    echo "usage: sh scripts/set-version.sh <semver>" >&2
    exit 2
fi

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

sed -i "s|<version>[^<]*</version>|<version>$VERSION</version>|" appinfo/info.xml
sed -i "s|^version = \".*\"|version = \"$VERSION\"|" pyproject.toml
sed -i "s|^__version__ = \".*\"|__version__ = \"$VERSION\"|" citizens/__init__.py
sed -i "s|app_version: str = \".*\"|app_version: str = \"$VERSION\"|" citizens/config.py
sed -i "s|APP_VERSION=\".*\"|APP_VERSION=\"$VERSION\"|" scripts/dev-env.sh
python3 - "$VERSION" <<'PY'
import json, pathlib, sys
version = sys.argv[1]
path = pathlib.Path("frontend/package.json")
data = json.loads(path.read_text())
data["version"] = version
path.write_text(json.dumps(data, indent=2) + "\n")
PY

# the image tag AppAPI pulls must match the released version
sed -i "s|<image-tag>[^<]*</image-tag>|<image-tag>$VERSION</image-tag>|" appinfo/info.xml

echo "version set to $VERSION"
