#!/bin/sh
# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Check a running Vosk server the way an assembly uses it. Needs a real server,
# because the bugs this catches do not exist in a mock:
#
#   * two connections loading a model AT THE SAME MOMENT — an import-time
#     asyncio.Lock binds to the wrong event loop on Python 3.9 and crashes, but
#     only under contention. Two connections that happen to serialise pass, so
#     this test starts both behind a barrier.
#   * a model being evicted while a round is still recording, which would
#     reload it into a second copy instead of saving memory.
#
#   scripts/vosk-check.sh [ws://citizens-vosk:2700]
set -eu

URL=${1:-ws://citizens-vosk:2700}
NETWORK=${VOSK_NETWORK:-nextcloud_nextcloud-network}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

docker run --rm --user root --network "$NETWORK" \
    -v "$REPO":/app -w /app --entrypoint sh citizens-test \
    -c "VOSK_CHECK_URL='$URL' python scripts/vosk/check_concurrency.py"
