#!/bin/sh
# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Run a self-hosted Vosk speech-to-text server for Citizens.
#
# ONE container serves every language: each session names the model it wants,
# and the app maps assembly language -> model name. Models load on first use and
# are freed again when idle, so an idle server costs a few MB.
#
# This script downloads nothing. Add a language with:
#     scripts/vosk-model.sh vosk-model-small-de-0.15
#
# Vosk has no authentication, so the port is published on 127.0.0.1 only. The
# app does not use it — it reaches the container by name on the shared Nextcloud
# network — but it makes manual testing possible from this host.
set -eu

CONTAINER=citizens-vosk
IMAGE=alphacep/kaldi-vosk-server:latest
NETWORK=${VOSK_NETWORK:-nextcloud_nextcloud-network}
HOST_PORT=${VOSK_HOST_PORT:-2700}
ROOT=${VOSK_ROOT:-/srv/citizens-vosk}
MEMORY=${VOSK_MEMORY:-900m}
# how many languages may be live at the same time; idle eviction (below)
# is what actually frees memory between assemblies
CACHE=${VOSK_MODEL_CACHE:-2}
IDLE=${VOSK_MODEL_IDLE_SECONDS:-1800}

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

mkdir -p "$ROOT/models"

# our patched server: per-connection model selection, and models freed when
# idle. See the header of scripts/vosk/asr_server.py for why.
cp "$SCRIPT_DIR/vosk/asr_server.py" "$ROOT/asr_server.py"

installed=$(find "$ROOT/models" -mindepth 1 -maxdepth 1 -type d | wc -l)
if [ "$installed" -eq 0 ]; then
    echo "No models installed yet. Add one before recording, for example:"
    echo "  scripts/vosk-model.sh vosk-model-small-it-0.22"
    echo
fi
# any installed model is a usable default for a session that names none
DEFAULT_MODEL=$(find "$ROOT/models" -mindepth 1 -maxdepth 1 -type d | sort | head -1)
DEFAULT_MODEL=${DEFAULT_MODEL:+/models/$(basename "$DEFAULT_MODEL")}

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d \
    --name "$CONTAINER" \
    --restart unless-stopped \
    --network "$NETWORK" \
    --memory "$MEMORY" \
    -p "127.0.0.1:${HOST_PORT}:2700" \
    -v "$ROOT/models:/models:ro" \
    -v "$ROOT/asr_server.py:/opt/asr_server.py:ro" \
    -e VOSK_SAMPLE_RATE=16000 \
    -e VOSK_MODEL_CACHE="$CACHE" \
    -e VOSK_MODEL_IDLE_SECONDS="$IDLE" \
    "$IMAGE" \
    python3 /opt/asr_server.py "${DEFAULT_MODEL:-/models/none}" >/dev/null

echo "Vosk is running as '$CONTAINER' on network $NETWORK."
echo "  docker logs -f $CONTAINER"
echo
echo "Settings -> Audio -> Vosk:"
echo "  Server URL   ws://${CONTAINER}:2700"
echo "  Models installed:"
if [ "$installed" -gt 0 ]; then
    for d in "$ROOT/models"/*; do
        [ -d "$d" ] && echo "    $(basename "$d")"
    done
else
    echo "    (none yet — scripts/vosk-model.sh <model-name>)"
fi
echo
echo "Models load on first use and are freed after ${IDLE}s idle (cache: $CACHE)."
