# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Decode the phone's live chunk stream into PCM for caption engines.

The phone uploads fragments of ONE continuous WebM/Opus stream: only the first
chunk carries container headers, so a later chunk cannot be decoded on its own.
Deepgram accepts the container stream directly; Vosk, Mistral Voxtral Realtime
and Whisper endpoints all want raw PCM. One long-lived ffmpeg per recording
turns the former into the latter.

Everything here is best-effort by design (brief §51): if ffmpeg dies or the
audio is undecodable, captions stop and the recording is untouched.
"""

import asyncio

from citizens.logging_setup import get_logger

log = get_logger(__name__)

SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2  # s16le mono
READ_SIZE = 8192
# a caption engine that stops draining must not grow memory without bound
MAX_QUEUED_PCM_BYTES = BYTES_PER_SECOND * 120


class PcmStream:
    """A persistent ffmpeg decoder for one recording's chunk stream."""

    def __init__(self, recording_id: str):
        self.recording_id = recording_id
        self.process: asyncio.subprocess.Process | None = None
        self.pcm: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.failed = False
        self._queued_bytes = 0
        self._reader: asyncio.Task | None = None

    async def start(self) -> bool:
        try:
            self.process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-hide_banner", "-loglevel", "error",
                # without these ffmpeg buffers ~1 s before emitting anything
                "-fflags", "nobuffer", "-flags", "low_delay",
                "-i", "pipe:0",
                "-f", "s16le", "-acodec", "pcm_s16le",
                "-ac", "1", "-ar", str(SAMPLE_RATE),
                "pipe:1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            log.warning("pcm_stream_start_failed", recording_id=self.recording_id, exc_info=True)
            self.failed = True
            return False
        self._reader = asyncio.create_task(self._read_loop())
        return True

    async def _read_loop(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            while True:
                data = await self.process.stdout.read(READ_SIZE)
                if not data:
                    break
                if self._queued_bytes > MAX_QUEUED_PCM_BYTES:
                    # the consumer is not keeping up; drop rather than grow
                    continue
                self._queued_bytes += len(data)
                self.pcm.put_nowait(data)
        except Exception:
            log.warning("pcm_stream_read_failed", recording_id=self.recording_id, exc_info=True)
        finally:
            self.pcm.put_nowait(None)

    def feed(self, chunk: bytes) -> None:
        """Append one uploaded chunk. Order matters: the stream is continuous."""
        if self.failed or self.process is None or self.process.stdin is None:
            return
        try:
            self.process.stdin.write(chunk)
        except (BrokenPipeError, ConnectionResetError, RuntimeError):
            # ffmpeg gone: captions end here, the recording is unaffected
            log.warning("pcm_stream_write_failed", recording_id=self.recording_id)
            self.failed = True

    async def read(self) -> bytes | None:
        """Next decoded PCM block, or None when the stream ended."""
        data = await self.pcm.get()
        if data is not None:
            self._queued_bytes -= len(data)
        return data

    async def close(self) -> None:
        if self.process is None:
            return
        try:
            if self.process.stdin is not None and not self.process.stdin.is_closing():
                self.process.stdin.close()
        except Exception:
            pass
        if self._reader is not None:
            try:
                await asyncio.wait_for(self._reader, timeout=10)
            except (TimeoutError, asyncio.CancelledError):
                self._reader.cancel()
        try:
            self.process.kill()
        except ProcessLookupError:
            pass
        self.process = None


def frames(pcm: bytes, seconds: float) -> list[bytes]:
    """Split PCM into fixed-duration frames (Vosk wants ~250 ms; feeding one
    10 s block would return a single result and behave like batch)."""
    size = int(BYTES_PER_SECOND * seconds)
    size -= size % 2  # never split a sample
    if size <= 0:
        return [pcm]
    return [pcm[offset : offset + size] for offset in range(0, len(pcm), size)]


def wav_bytes(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw PCM in a WAV container for endpoints that need a real file."""
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buffer.getvalue()
