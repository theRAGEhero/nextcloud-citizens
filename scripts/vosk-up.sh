#!/bin/sh
# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Run a self-hosted Vosk speech-to-text server for testing Citizens.
#
# ONE container serves EVERY language: each session names the model it wants in
# its config frame, and the app maps assembly language -> model path. Adding a
# language is one line in MODELS below plus one row in Settings.
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

# language:model-name — small models, enough for testing the pipeline
MODELS="it:vosk-model-small-it-0.22 en:vosk-model-small-en-us-0.15"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

mkdir -p "$ROOT/models"

for entry in $MODELS; do
    lang=${entry%%:*}
    name=${entry#*:}
    target="$ROOT/models/$lang"
    if [ -d "$target" ] && [ -f "$target/am/final.mdl" ]; then
        echo "model $lang already present ($name)"
        continue
    fi
    echo "downloading $name for '$lang'..."
    rm -rf "$target" "$ROOT/models/.tmp"
    mkdir -p "$ROOT/models/.tmp"
    curl -fSL --retry 3 -o "$ROOT/models/.tmp/model.zip" \
        "https://alphacephei.com/vosk/models/${name}.zip"
    unzip -q "$ROOT/models/.tmp/model.zip" -d "$ROOT/models/.tmp"
    # the archive contains a single top-level directory named after the model
    mv "$ROOT/models/.tmp/$name" "$target"
    rm -rf "$ROOT/models/.tmp"
    echo "  -> $target"
done

# our patched server: per-connection model selection and a load cache.
# See the header of scripts/vosk/asr_server.py for why.
cp "$SCRIPT_DIR/vosk/asr_server.py" "$ROOT/asr_server.py"

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
    "$IMAGE" \
    python3 /opt/asr_server.py /models/en >/dev/null

echo
echo "Vosk is starting as '$CONTAINER' on network $NETWORK."
echo "Watch it load:   docker logs -f $CONTAINER"
echo
echo "Settings -> Speech to text -> Vosk:"
echo "  Server URL          ws://${CONTAINER}:2700"
echo "  Model for Italian   /models/it"
echo "  Model for English   /models/en"
echo
echo "(from this host, for manual testing only: ws://127.0.0.1:${HOST_PORT})"
