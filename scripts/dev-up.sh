#!/bin/sh
# Build the dev image and (re)start the Citizens dev container with the
# source bind-mounted and uvicorn auto-reload. Nextcloud reaches it as
# http://nc_app_citizens:23000 on the shared docker network.
set -eu
. "$(dirname "$0")/dev-env.sh"

docker build -q -t "$IMAGE" "$REPO_DIR" >/dev/null
docker volume create "$DATA_VOLUME" >/dev/null
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d \
    --name "$CONTAINER" \
    --network "$NETWORK" \
    --restart unless-stopped \
    --memory 512m --memory-swap 512m \
    -v "$REPO_DIR":/app \
    -v "$DATA_VOLUME":/data \
    -e APP_ID="$APP_ID" \
    -e APP_VERSION="$APP_VERSION" \
    -e APP_HOST=0.0.0.0 \
    -e APP_PORT="$APP_PORT" \
    -e APP_SECRET="$APP_SECRET" \
    -e NEXTCLOUD_URL="$NEXTCLOUD_URL" \
    -e APP_PERSISTENT_STORAGE=/data \
    -e CITIZENS_DEV=1 \
    -e CITIZENS_LOG_LEVEL=DEBUG \
    --entrypoint sh \
    "$IMAGE" \
    -c "cd /app && exec python3 -m uvicorn citizens.main:APP --host 0.0.0.0 --port $APP_PORT --reload" \
    >/dev/null
echo "Container $CONTAINER running on $NETWORK (port $APP_PORT)."
