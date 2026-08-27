#!/bin/sh
# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Stop the Vosk server. Downloaded models are kept, so vosk-up.sh restarts in
# seconds; pass --purge to remove them too.
set -eu

CONTAINER=citizens-vosk
ROOT=${VOSK_ROOT:-/srv/citizens-vosk}

docker rm -f "$CONTAINER" >/dev/null 2>&1 && echo "stopped $CONTAINER" || echo "$CONTAINER was not running"

if [ "${1:-}" = "--purge" ]; then
    rm -rf "$ROOT/models"
    echo "removed downloaded models from $ROOT/models"
fi
