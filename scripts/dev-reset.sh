#!/bin/sh
# Delete ONLY Citizens application data (SQLite DB, recordings, logs) from the
# dev data volume. This must NEVER touch Nextcloud data (brief §58).
set -eu
. "$(dirname "$0")/dev-env.sh"

printf 'This deletes ALL Citizens app data in volume %s. Continue? [y/N] ' "$DATA_VOLUME"
read -r answer
case "$answer" in
    y|Y) ;;
    *) echo "Aborted."; exit 1 ;;
esac

docker run --rm -v "$DATA_VOLUME":/data alpine:3 sh -c 'rm -rf /data/* /data/.[!.]* 2>/dev/null || true'
docker restart "$CONTAINER" >/dev/null 2>&1 || true
echo "Citizens data volume cleared."
