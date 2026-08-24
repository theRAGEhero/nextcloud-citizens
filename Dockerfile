FROM python:3.12-slim

# espeak-ng: synthetic speech for end-to-end transcription tests
# fonts-dejavu-core: Unicode font embedded in PDF reports
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg espeak-ng fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY citizens ./citizens
COPY appinfo ./appinfo
COPY js ./js
COPY img ./img
COPY start.sh ./
RUN pip install --no-cache-dir . && chmod +x start.sh

ENV APP_PERSISTENT_STORAGE=/data

ENTRYPOINT ["./start.sh"]
