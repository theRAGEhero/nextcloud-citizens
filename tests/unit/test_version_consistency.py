# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every place that states the app version must agree.

The App Store matches a release against <version> in appinfo/info.xml, AppAPI
registers what it finds there, and the recorder busts its asset cache with the
version the running app reports — a mismatch ships a release that advertises
the wrong version.
"""

import json
import pathlib
import re

import citizens

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _search(path: pathlib.Path, pattern: str) -> str:
    match = re.search(pattern, path.read_text(), re.MULTILINE)
    assert match, f"version not found in {path}"
    return match.group(1)


def test_all_version_declarations_match():
    versions = {
        "citizens/__init__.py": citizens.__version__,
        "appinfo/info.xml": _search(ROOT / "appinfo/info.xml", r"<version>([^<]+)</version>"),
        "appinfo/info.xml image-tag": _search(
            ROOT / "appinfo/info.xml", r"<image-tag>([^<]+)</image-tag>"
        ),
        "pyproject.toml": _search(ROOT / "pyproject.toml", r'^version = "([^"]+)"'),
        "citizens/config.py": _search(
            ROOT / "citizens/config.py", r'app_version: str = "([^"]+)"'
        ),
        "scripts/dev-env.sh": _search(ROOT / "scripts/dev-env.sh", r'APP_VERSION="([^"]+)"'),
        "frontend/package.json": json.loads((ROOT / "frontend/package.json").read_text())["version"],
    }
    assert len(set(versions.values())) == 1, versions
