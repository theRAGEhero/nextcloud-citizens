# Nextcloud Citizens — ExApp runtime image.
#
# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Build with --build-arg WITH_TEST_TOOLS=1 for the image `make test` uses
# (adds espeak-ng for synthetic-speech transcription tests). The published
# image never carries test tooling.
FROM python:3.12-slim

ARG WITH_TEST_TOOLS=0

# ffmpeg: audio assembly/validation. fonts-dejavu-core: Unicode font embedded
# in PDF reports. curl: container HEALTHCHECK.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core curl \
    && if [ "$WITH_TEST_TOOLS" = "1" ]; then apt-get install -y --no-install-recommends espeak-ng; fi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY citizens ./citizens
COPY appinfo ./appinfo
# UI bundles: the organizer app (js + css) and the public table recorder.
# Missing any of these leaves the deployed app unstyled or the recorder dead.
COPY js ./js
COPY css ./css
COPY img ./img
COPY recorder_static ./recorder_static
COPY start.sh ./
RUN pip install --no-cache-dir . && chmod +x start.sh

# APP_HOST: nc_py_api's run_app defaults to 127.0.0.1, which is unreachable
# from Nextcloud; a container must listen on all interfaces. AppAPI normally
# injects these three, but the image must be correct on its own.
ENV APP_PERSISTENT_STORAGE=/data \
    APP_HOST=0.0.0.0 \
    APP_PORT=23000

# AppAPI mounts the persistent volume at /data; the service must own it.
RUN useradd --system --uid 10001 --home-dir /app citizens \
    && mkdir -p /data \
    && chown -R citizens:citizens /app /data
USER citizens

EXPOSE 23000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${APP_PORT}/heartbeat" || exit 1

ENTRYPOINT ["./start.sh"]
