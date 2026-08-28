#!/bin/sh
# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Download one Vosk model, by name, ready for a language you are about to use.
# Nothing is downloaded automatically: an assembly uses one language, and the
# next one may be days away in another.
#
#   scripts/vosk-model.sh vosk-model-small-de-0.15
#   scripts/vosk-model.sh --list
#
# The name you pass is the name you type into Settings.
set -eu

ROOT=${VOSK_ROOT:-/srv/citizens-vosk}

SUGGESTED="vosk-model-small-en-us-0.15  English
vosk-model-small-it-0.22     Italiano
vosk-model-small-de-0.15     Deutsch
vosk-model-small-fr-0.22     Français
vosk-model-small-es-0.42     Español"

usage() {
    echo "usage: $0 <model-name>    (browse them at https://alphacephei.com/vosk/models)"
    echo
    echo "Small models for the languages an assembly can use:"
    echo "$SUGGESTED" | sed 's/^/  /'
    echo
    echo "Installed:"
    if [ -d "$ROOT/models" ] && [ -n "$(ls -A "$ROOT/models" 2>/dev/null)" ]; then
        for d in "$ROOT/models"/*; do
            [ -d "$d" ] && echo "  $(basename "$d")"
        done
    else
        echo "  (none)"
    fi
}

if [ $# -lt 1 ] || [ "$1" = "--list" ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
    [ "${1:-}" = "--list" ] && exit 0
    [ $# -lt 1 ] && exit 2
    exit 0
fi

NAME=$1
TARGET="$ROOT/models/$NAME"

if [ -d "$TARGET" ]; then
    echo "$NAME is already installed at $TARGET"
    exit 0
fi

mkdir -p "$ROOT/models/.tmp"
echo "downloading $NAME..."
if ! curl -fSL --retry 3 -o "$ROOT/models/.tmp/model.zip" \
        "https://alphacephei.com/vosk/models/${NAME}.zip"; then
    rm -rf "$ROOT/models/.tmp"
    echo "could not download '$NAME' — check the name at https://alphacephei.com/vosk/models" >&2
    exit 1
fi
unzip -q "$ROOT/models/.tmp/model.zip" -d "$ROOT/models/.tmp"
# the archive holds a single top-level directory named after the model
if [ -d "$ROOT/models/.tmp/$NAME" ]; then
    mv "$ROOT/models/.tmp/$NAME" "$TARGET"
else
    inner=$(find "$ROOT/models/.tmp" -mindepth 1 -maxdepth 1 -type d ! -name .tmp | head -1)
    mv "$inner" "$TARGET"
fi
rm -rf "$ROOT/models/.tmp"

echo "installed $NAME"
echo
echo "In Settings -> Audio -> Vosk, put this name against its language."
echo "It loads on first use and is freed again when idle; no restart needed."
