#!/usr/bin/env python3
"""Validate appinfo/info.xml exactly the way the Nextcloud App Store does.

The store runs pre-info.xslt first (which drops elements it does not know,
including the <routes> block that AppAPI reads from our release tarball) and
only then validates against info.xsd. Validating raw against the XSD reports a
false failure on <routes>, so replicate the real pipeline.

SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
SPDX-License-Identifier: AGPL-3.0-or-later
"""

import pathlib
import sys

import requests
from lxml import etree

SCHEMA_URL = "https://apps.nextcloud.com/schema/apps/info.xsd"
XSLT_URL = (
    "https://raw.githubusercontent.com/nextcloud/appstore/master/"
    "nextcloudappstore/api/v1/release/pre-info.xslt"
)
INFO_XML = pathlib.Path(__file__).resolve().parents[1] / "appinfo" / "info.xml"


def fetch(url: str) -> bytes:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def main() -> int:
    document = etree.parse(str(INFO_XML))
    transform = etree.XSLT(etree.fromstring(fetch(XSLT_URL)).getroottree())
    schema = etree.XMLSchema(etree.fromstring(fetch(SCHEMA_URL)).getroottree())

    cleaned = transform(document)
    if not schema.validate(cleaned):
        for error in schema.error_log:
            print(f"line {error.line}: {error.message}", file=sys.stderr)
        return 1

    # what the store never sees, but AppAPI needs from the tarball
    external = document.find("external-app")
    docker = external.find("docker-install") if external is not None else None
    if docker is None:
        print("external-app/docker-install is missing — the app would be "
              "uninstallable (deployMethods: [])", file=sys.stderr)
        return 1
    routes = external.findall("routes/route")
    if not routes:
        print("no <routes> declared — nothing would reach the app through the "
              "AppAPI proxy", file=sys.stderr)
        return 1
    for route in routes:
        level = route.findtext("access_level", "")
        if level not in ("PUBLIC", "USER", "ADMIN", "0", "1", "2"):
            print(f"invalid access_level {level!r}", file=sys.stderr)
            return 1

    image = "/".join(
        filter(None, (docker.findtext("registry"), docker.findtext("image")))
    )
    print(f"info.xml OK — {image}:{docker.findtext('image-tag')}, {len(routes)} routes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
