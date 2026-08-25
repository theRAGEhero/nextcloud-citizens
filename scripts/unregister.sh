#!/bin/sh
# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
# Remove the Citizens ExApp registration from AppAPI. Never touches Nextcloud
# itself beyond that.
set -eu
. "$(dirname "$0")/dev-env.sh"

occ app_api:app:unregister "$APP_ID" --force || true
