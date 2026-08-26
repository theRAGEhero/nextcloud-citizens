# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Whisper transcription through any OpenAI-compatible endpoint.

Verified 2026-08-26 against the OpenAI audio API and the self-hosted servers
that reimplement it (Speaches, whisper.cpp server, LocalAI, vLLM,
whisperx-api-server): POST {base}/audio/transcriptions, multipart, with
`response_format=verbose_json` and repeated `timestamp_granularities[]` fields.

Three response shapes are handled by one normalizer:

* plain `verbose_json` — segments with no speaker at all (the OpenAI default),
* `verbose_json` whose segments carry a `speaker` (whisperx-api-server with
  `diarize=true`, hwdsl2/docker-whisper with its diarization flag),
* `diarized_json` from OpenAI's gpt-4o-transcribe-diarize, which has speakers
  but no word timings.

Note that in `verbose_json` the words array is a FLAT top-level list, not
nested inside segments, so words are assigned to segments by time overlap.
"""

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

import httpx

from citizens.logging_setup import get_logger
from citizens.providers.transcription.base import (
    NormalizedSegment,
    NormalizedTranscript,
    NormalizedWord,
    SpeakerLabeler,
    TranscriptionError,
)

log = get_logger(__name__)

BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "whisper-1"
# OpenAI rejects uploads above 25 MB; re-encode before we get close to it
MAX_UPLOAD_BYTES = 24 * 1024 * 1024

EXTENSION_BY_MIME = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a"}


def transcribe_file(
    api_key: str,
    path: Path,
    mime_type: str,
    language: str,
    model: str = DEFAULT_MODEL,
    base_url: str = BASE_URL,
) -> NormalizedTranscript:
    model = model or DEFAULT_MODEL
    diarizing = "diarize" in model.lower()
    content_type = (mime_type or "audio/webm").split(";")[0].strip()
    suffix = EXTENSION_BY_MIME.get(content_type, ".webm")

    upload_path, cleanup = _prepare_upload(path, suffix)
    data: dict[str, str] = {"model": model}
    if language:
        data["language"] = language
    if diarizing:
        # the diarizing model returns speakers but no word timings, and
        # refuses inputs over 30 s without an explicit chunking strategy
        data["response_format"] = "diarized_json"
        data["chunking_strategy"] = "auto"
        files_extra: list[tuple[str, tuple]] = []
    else:
        data["response_format"] = "verbose_json"
        files_extra = [
            ("timestamp_granularities[]", (None, "segment")),
            ("timestamp_granularities[]", (None, "word")),
        ]

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    endpoint = f"{(base_url or BASE_URL).rstrip('/')}/audio/transcriptions"

    try:
        with upload_path.open("rb") as handle:
            files = [("file", (upload_path.name, handle, content_type))]
            files.extend(files_extra)
            response = httpx.post(
                endpoint,
                headers=headers,
                data=data,
                files=files,
                timeout=httpx.Timeout(900, connect=30),
            )
    except httpx.HTTPError as exc:
        raise TranscriptionError(f"Whisper request failed: {type(exc).__name__}") from exc
    finally:
        cleanup()

    if response.status_code in (401, 403):
        raise TranscriptionError(
            f"Whisper endpoint authentication failed ({response.status_code})", permanent=True
        )
    if response.status_code in (400, 413, 415, 422):
        raise TranscriptionError(
            f"Whisper endpoint rejected the audio: {response.text[:300]}", permanent=True
        )
    if response.status_code == 404:
        raise TranscriptionError(
            f"No transcription endpoint at {endpoint} — check the base URL", permanent=True
        )
    if response.status_code != 200:
        raise TranscriptionError(f"Whisper endpoint returned HTTP {response.status_code}")

    try:
        raw = response.json()
    except ValueError as exc:
        raise TranscriptionError("Whisper endpoint returned a non-JSON response") from exc
    return normalize(raw, model=model, requested_language=language)


def _prepare_upload(path: Path, suffix: str) -> tuple[Path, Callable[[], None]]:
    """Hosted OpenAI caps uploads at 25 MB. Long recordings are re-encoded to
    low-bitrate mono Opus (ffmpeg is already in the image) rather than failing."""
    if path.stat().st_size <= MAX_UPLOAD_BYTES:
        return path, lambda: None

    handle = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    handle.close()
    target = Path(handle.name)
    result = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(path),
         "-ac", "1", "-c:a", "libopus", "-b:a", "24k", str(target)],
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0 or not target.exists():
        target.unlink(missing_ok=True)
        raise TranscriptionError(
            f"Could not compress audio for upload: {result.stderr[-300:]}", permanent=True
        )
    log.info(
        "whisper_audio_recompressed",
        original_bytes=path.stat().st_size,
        upload_bytes=target.stat().st_size,
    )
    return target, lambda: target.unlink(missing_ok=True)


def normalize(raw: dict, model: str, requested_language: str) -> NormalizedTranscript:
    labeler = SpeakerLabeler()
    segments: list[NormalizedSegment] = []
    raw_segments = raw.get("segments") or []
    flat_words = raw.get("words") or []

    for item in raw_segments:
        start = float(item.get("start", 0.0))
        end = float(item.get("end", 0.0))
        segments.append(
            NormalizedSegment(
                # present only on diarizing servers/models; "" otherwise
                speaker=labeler.label(item.get("speaker")),
                start=start,
                end=end,
                text=(item.get("text") or "").strip(),
                words=_words_within(flat_words, start, end),
            )
        )

    if not segments and (raw.get("text") or "").strip():
        # response_format=json, or a server that omits segments entirely
        segments.append(
            NormalizedSegment(
                speaker="",
                start=0.0,
                end=float(raw.get("duration", 0.0) or 0.0),
                text=raw["text"].strip(),
                words=_as_words(flat_words),
            )
        )

    return NormalizedTranscript(
        provider="whisper",
        model=model,
        language=(raw.get("language") or "") or requested_language,
        segments=[s for s in segments if s.text],
        raw=raw,
    )


def _words_within(flat_words: list, start: float, end: float) -> list[NormalizedWord]:
    """verbose_json puts every word in one top-level list; assign each to the
    segment it overlaps (midpoint inside the segment's span)."""
    inside = []
    for word in flat_words:
        try:
            word_start = float(word.get("start", 0.0))
            word_end = float(word.get("end", word_start))
        except (TypeError, ValueError):
            continue
        midpoint = (word_start + word_end) / 2
        if start <= midpoint <= end:
            inside.append(
                NormalizedWord(text=word.get("word") or "", start=word_start, end=word_end)
            )
    return inside


def _as_words(flat_words: list) -> list[NormalizedWord]:
    return [
        NormalizedWord(
            text=word.get("word") or "",
            start=float(word.get("start", 0.0)),
            end=float(word.get("end", 0.0)),
        )
        for word in flat_words
    ]


def probe_models(base_url: str, api_key: str, timeout: float = 15.0) -> httpx.Response:
    """Cheap reachability check used by the admin Test button."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    return httpx.get(
        f"{(base_url or BASE_URL).rstrip('/')}/models", headers=headers, timeout=timeout
    )
