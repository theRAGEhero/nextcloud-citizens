# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every route must use an HTTP verb the AppAPI proxy can actually forward.

AppAPI publishes proxy handlers for GET, POST, PUT and DELETE only
(ExAppProxy#ExAppGet/Post/Put/Delete in app_api/appinfo/routes.php). A PATCH
to /apps/app_api/proxy/citizens/... is answered 405 by Nextcloud's own router:
it never reaches this app, and our <routes> table is never consulted.

Finding review (Approve/Reject) shipped broken for exactly that reason, and the
rest of the suite cannot see this class of bug — TestClient talks to FastAPI
directly, so it bypasses the proxy that does the rejecting.

Routes come from app.openapi() rather than app.routes: since FastAPI 0.141
app.routes holds unexpanded _IncludedRouter placeholders, so walking it finds
no endpoints at all and every assertion here would pass vacuously.
"""

import pathlib
import re
import xml.etree.ElementTree as ElementTree

import pytest

from citizens.main import create_app

ROOT = pathlib.Path(__file__).resolve().parents[2]

PROXYABLE = {"GET", "POST", "PUT", "DELETE"}


@pytest.fixture(scope="module")
def routes() -> list[tuple[str, str]]:
    """(path, METHOD) for the user-facing API. /heartbeat, /init and /enabled
    are AppAPI's own callbacks and do not travel through the user proxy."""
    paths = create_app(with_auth=False).openapi()["paths"]
    found = [
        (path, method.upper())
        for path, operations in paths.items()
        for method in operations
        if path.startswith("/api/v1/") or path.startswith("/recorder")
    ]
    # the placeholder trap above: if the inventory ever comes back empty or
    # missing a route we know exists, these tests are not testing anything
    assert len(found) > 40, f"route inventory looks wrong: {len(found)} routes"
    assert any(path == "/api/v1/findings/{finding_id}" for path, _ in found)
    return found


def _declared_routes() -> list[tuple[str, set[str]]]:
    root = ElementTree.parse(ROOT / "appinfo" / "info.xml").getroot()
    return [
        (
            route.findtext("url", ""),
            {verb.strip().upper() for verb in route.findtext("verb", "").split(",")},
        )
        for route in root.findall("external-app/routes/route")
    ]


def test_no_route_uses_a_verb_the_proxy_cannot_forward(routes):
    offenders = [f"{method} {path}" for path, method in routes if method not in PROXYABLE]
    assert not offenders, f"unreachable through the AppAPI proxy: {offenders}"


def test_info_xml_declares_every_verb_the_api_uses(routes):
    """AppAPI 34+ matches path AND verb together, so an undeclared verb does
    not merely fail — it falls through to the next entry that does match. An
    admin route whose verb is missing from the ADMIN entry would be served by
    the USER catch-all instead: a privilege downgrade, not a 405."""
    declared = _declared_routes()
    undeclared, downgraded = [], []
    for path, method in routes:
        if method not in PROXYABLE:
            continue  # reported by the test above
        proxy_path = path.lstrip("/")
        matches = [
            url
            for url, verbs in declared
            if re.search(url, proxy_path, re.IGNORECASE) and method in verbs
        ]
        if not matches:
            undeclared.append(f"{method} {proxy_path}")
        elif proxy_path.startswith("api/v1/admin/") and "admin" not in matches[0]:
            downgraded.append(f"{method} {proxy_path} would be served by {matches[0]}")
    assert not undeclared, f"no <route> declares these: {undeclared}"
    assert not downgraded, f"admin routes escaping the ADMIN entry: {downgraded}"


def test_frontend_clients_never_send_an_unproxyable_verb():
    for client in ("frontend/src/api.ts", "frontend/src/recorder/api.ts"):
        source = (ROOT / client).read_text()
        for verb in ("PATCH", "TRACE", "CONNECT"):
            assert f"'{verb}'" not in source, f"{client} sends {verb}, which the proxy drops"
