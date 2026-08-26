# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vosk transcription over the vosk-server WebSocket protocol.

Verified 2026-08-26 against alphacep/vosk-server (websocket/asr_server.py).
Vosk has no HTTP batch API: audio is streamed as raw 16 kHz mono s16le PCM
frames, results come back one message per frame (partial or final), and the
stream is closed with an end-of-file message.

Two things about this protocol will bite anyone reading the docs only:

* the server compares the terminator with a LITERAL string,
  `if message == '{"eof" : 1}'` — json.dumps produces `{"eof": 1}` and would be
  fed to the recognizer as audio, so EOF_MESSAGE below is byte-exact;
* it accepts nothing but headerless PCM, so the canonical recording is decoded
  with ffmpeg first (already in the image).

Vosk returns word timings but no punctuation, no capitalisation and no
diarization — every segment therefore carries an empty speaker label.
"""

import asyncio
import json
import subprocess
from pathlib import Path

from citizens.logging_setup import get_logger
from citizens.providers.transcription.base import (
    NormalizedSegment,
    NormalizedTranscript,
    NormalizedWord,
    TranscriptionError,
)

log = get_logger(__name__)

BASE_URL = "ws://localhost:2700"
DEFAULT_MODEL = ""  # the server decides; the model path is server-side config
SAMPLE_RATE = 16000
# 0.2 s of audio per frame, as in the reference client
FRAME_BYTES = int(SAMPLE_RATE * 0.2) * 2
EOF_MESSAGE = '{"eof" : 1}'  # byte-exact: the server does a string comparison


def transcribe_file(
    api_key: str,
    path: Path,
    mime_type: str,
    language: str,
    model: str = DEFAULT_MODEL,
    base_url: str = BASE_URL,
) -> NormalizedTranscript:
    """`api_key` is unused (vosk-server has no authentication) but kept so every
    provider adapter has the same signature."""
    pcm = _decode_to_pcm(path)
    raw = asyncio.run(_stream(base_url or BASE_URL, pcm))
    return normalize(raw, model=model, requested_language=language)


def _decode_to_pcm(path: Path) -> bytes:
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-ar", str(SAMPLE_RATE), "-ac", "1", "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1"],
        capture_output=True,
        timeout=900,
    )
    if result.returncode != 0:
        raise TranscriptionError(
            f"Could not decode audio for Vosk: {result.stderr.decode()[-300:]}", permanent=True
        )
    if not result.stdout:
        raise TranscriptionError("Audio decoded to an empty PCM stream", permanent=True)
    return result.stdout


async def _stream(url: str, pcm: bytes) -> dict:
    try:
        from websockets.asyncio.client import connect
    except ImportError:  # older websockets
        from websockets import connect  # type: ignore[no-redef]

    results: list[dict] = []
    try:
        async with connect(url, max_size=None, open_timeout=30) as websocket:
            await websocket.send(
                json.dumps({"config": {"sample_rate": SAMPLE_RATE, "words": True}})
            )
            for offset in range(0, len(pcm), FRAME_BYTES):
                await websocket.send(pcm[offset : offset + FRAME_BYTES])
                # the server answers exactly once per audio frame
                _collect(results, await websocket.recv())
            await websocket.send(EOF_MESSAGE)
            _collect(results, await websocket.recv())
    except (OSError, TimeoutError) as exc:
        raise TranscriptionError(f"Vosk server unreachable at {url}: {type(exc).__name__}") from exc
    except Exception as exc:  # websockets raises its own hierarchy
        raise TranscriptionError(f"Vosk streaming failed: {type(exc).__name__}") from exc
    return {"results": results}


def _collect(results: list[dict], message) -> None:
    """Keep only final utterances; partials are progress, not transcript."""
    try:
        data = json.loads(message)
    except (TypeError, ValueError):
        return
    if "partial" in data:
        return
    if (data.get("text") or "").strip() or data.get("result"):
        results.append(data)


def normalize(raw: dict, model: str, requested_language: str) -> NormalizedTranscript:
    segments: list[NormalizedSegment] = []
    for item in raw.get("results") or []:
        words = [
            NormalizedWord(
                text=word.get("word") or "",
                start=float(word.get("start", 0.0)),
                end=float(word.get("end", 0.0)),
            )
            for word in item.get("result") or []
        ]
        text = (item.get("text") or "").strip()
        if not text and words:
            text = " ".join(word.text for word in words).strip()
        segments.append(
            NormalizedSegment(
                # Vosk does not diarize; the base class documents "" for this
                speaker="",
                start=words[0].start if words else 0.0,
                end=words[-1].end if words else 0.0,
                text=text,
                words=words,
            )
        )
    return NormalizedTranscript(
        provider="vosk",
        model=model or "vosk-server",
        language=requested_language,
        segments=[segment for segment in segments if segment.text],
        raw=raw,
    )


async def probe(url: str, timeout: float = 10.0) -> bool:
    """Admin Test button: open the socket, send a config frame, expect a reply."""
    try:
        from websockets.asyncio.client import connect
    except ImportError:  # older websockets
        from websockets import connect  # type: ignore[no-redef]

    async with connect(url or BASE_URL, open_timeout=timeout) as websocket:
        await websocket.send(json.dumps({"config": {"sample_rate": SAMPLE_RATE}}))
        # a config frame produces no reply, so send a short silence frame too
        await websocket.send(b"\x00" * FRAME_BYTES)
        await asyncio.wait_for(websocket.recv(), timeout=timeout)
        await websocket.send(EOF_MESSAGE)
    return True
