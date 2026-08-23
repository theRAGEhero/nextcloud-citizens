#!/bin/sh
# Remove the Citizens ExApp registration from AppAPI. Never touches Nextcloud
# itself beyond that.
set -eu
. "$(dirname "$0")/dev-env.sh"

occ app_api:app:unregister "$APP_ID" --force || true
