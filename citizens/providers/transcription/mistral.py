"""Mistral (Voxtral) batch transcription adapter.

API verified against docs 2026-08-23: POST /v1/audio/transcriptions
(multipart), model `voxtral-mini-latest` (Voxtral Mini Transcribe 2),
`diarize=true`, `timestamp_granularities` segment/word. Segment fields are
parsed defensively (docs don't publish the exact chunk schema).
"""

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

BASE_URL = "https://api.mistral.ai/v1/audio/transcriptions"
DEFAULT_MODEL = "voxtral-mini-latest"


def transcribe_file(
    api_key: str, path: Path, mime_type: str, language: str, model: str = DEFAULT_MODEL
) -> NormalizedTranscript:
    data: dict = {
        "model": model or DEFAULT_MODEL,
        "diarize": "true",
        "timestamp_granularities": "segment",
    }
    # per docs, language is incompatible with timestamp_granularities — prefer timestamps
    try:
        response = httpx.post(
            BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files={"file": (path.name, path.read_bytes(), mime_type.split(";")[0] or "audio/webm")},
            timeout=httpx.Timeout(600, connect=30),
        )
    except httpx.HTTPError as exc:
        raise TranscriptionError(f"Mistral request failed: {type(exc).__name__}") from exc

    if response.status_code in (401, 403):
        raise TranscriptionError(f"Mistral authentication failed ({response.status_code})", permanent=True)
    if response.status_code == 422:
        raise TranscriptionError(f"Mistral rejected the request: {response.text[:300]}", permanent=True)
    if response.status_code != 200:
        raise TranscriptionError(f"Mistral returned HTTP {response.status_code}")

    raw = response.json()
    return normalize(raw, model=model or DEFAULT_MODEL, requested_language=language)


def _first(mapping: dict, *keys, default=None):
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def normalize(raw: dict, model: str, requested_language: str) -> NormalizedTranscript:
    labeler = SpeakerLabeler()
    segments: list[NormalizedSegment] = []
    for chunk in raw.get("segments") or []:
        text = (_first(chunk, "text", "transcript", default="") or "").strip()
        if not text:
            continue
        segments.append(
            NormalizedSegment(
                speaker=labeler.label(_first(chunk, "speaker", "speaker_id", "speaker_label")),
                start=float(_first(chunk, "start", "start_seconds", default=0.0)),
                end=float(_first(chunk, "end", "end_seconds", default=0.0)),
                text=text,
                words=[
                    NormalizedWord(
                        text=_first(word, "text", "word", default="") or "",
                        start=float(_first(word, "start", default=0.0)),
                        end=float(_first(word, "end", default=0.0)),
                    )
                    for word in chunk.get("words") or []
                ],
            )
        )
    if not segments and (raw.get("text") or "").strip():
        segments.append(
            NormalizedSegment(speaker="", start=0.0, end=0.0, text=raw["text"].strip())
        )
    return NormalizedTranscript(
        provider="mistral",
        model=model,
        language=raw.get("language") or requested_language or "",
        segments=segments,
        raw=raw,
    )
