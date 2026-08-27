# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Provisional live captions (brief §34, §51).

The phone's ~10 s chunks — already uploaded for safety — are forwarded into a
server-side Deepgram streaming session per recording, so live captions cost
the phone zero extra bandwidth or battery. Captions are PROVISIONAL; the
canonical transcript always comes from batch transcription of the complete
audio. Any failure here is low-severity by design: recording is never
affected, and a dead session backs off instead of reconnect-looping.

Every configured engine can produce them, through the protocol it actually
speaks: Deepgram (or any Deepgram-protocol server such as WhisperLiveKit)
takes the WebM stream directly, while Vosk, Mistral Voxtral Realtime and
Whisper endpoints are fed decoded PCM by citizens.services.live_audio.
"""

import asyncio
import base64
import json
import time
import urllib.parse
from collections import deque

from citizens.logging_setup import get_logger
from citizens.services import live_audio

log = get_logger(__name__)

DEEPGRAM_URL = "wss://api.deepgram.com/v1/listen"
MISTRAL_URL = "wss://api.mistral.ai/v1/audio/transcriptions/realtime"
SESSION_IDLE_TIMEOUT = 180.0
FAILURE_COOLDOWN = 60.0
KEEPALIVE_SECONDS = 5.0
MAX_LINES = 80
# byte-exact: vosk-server compares the terminator with a literal string
VOSK_EOF = '{"eof" : 1}'


class _BaseSession:
    """Shared caption-session state. Subclasses implement run() for one engine
    and append {"t", "text", "speaker"} entries to self.lines."""

    #: True when the engine consumes decoded PCM rather than the WebM stream
    wants_pcm = False

    def __init__(
        self,
        recording_id: str,
        api_key: str,
        model: str,
        language: str,
        endpoint: str = "",
    ):
        self.endpoint = endpoint
        self.recording_id = recording_id
        self.api_key = api_key
        self.model = model
        self.language = language
        self.queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=64)
        self.lines: deque[dict] = deque(maxlen=MAX_LINES)
        self.active = True
        self.failed_at: float | None = None
        self.last_fed = time.monotonic()
        self.task: asyncio.Task | None = None
        # engines fed with PCM own a decoder for this recording
        self.pcm_stream = None

    def add_line(self, text: str, start: float = 0.0, speaker=None) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._drop_provisional()
        self.lines.append({"t": start, "text": text, "speaker": speaker})

    def set_provisional(self, text: str, start: float = 0.0) -> None:
        """Show in-progress speech. Engines endpoint on pauses, so without this
        a table talking continuously would see nothing until they stop."""
        text = (text or "").strip()
        self._drop_provisional()
        if text:
            self.lines.append(
                {"t": start, "text": text, "speaker": None, "provisional": True}
            )
            self._has_provisional = True

    def _drop_provisional(self) -> None:
        if getattr(self, "_has_provisional", False) and self.lines:
            self.lines.pop()
        self._has_provisional = False

    async def run(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class DeepgramSession(_BaseSession):
    """Deepgram's streaming API, and any server speaking the same protocol
    (WhisperLiveKit's /v1/listen), which takes the WebM stream as-is."""

    async def run(self) -> None:
        try:
            from websockets.asyncio.client import connect
        except ImportError:  # older websockets
            from websockets import connect  # type: ignore[no-redef]

        params = {
            "model": self.model or "nova-3",
            "punctuate": "true",
            "smart_format": "true",
            "interim_results": "false",
            "diarize": "true",
        }
        if self.language:
            params["language"] = self.language
        base = self.endpoint or DEEPGRAM_URL
        headers = {}
        if self.api_key:
            if "api.deepgram.com" in base:
                headers["Authorization"] = f"Token {self.api_key}"
            else:
                # Deepgram-protocol servers (WhisperLiveKit) take a query token
                params["token"] = self.api_key
        url = base + ("&" if "?" in base else "?") + urllib.parse.urlencode(params)
        try:
            async with connect(url, additional_headers=headers) as ws:
                log.info("live_stt_session_started", recording_id=self.recording_id)
                sender = asyncio.create_task(self._send_loop(ws))
                keeper = asyncio.create_task(self._keepalive_loop(ws))
                try:
                    async for message in ws:
                        self._handle_message(message)
                finally:
                    sender.cancel()
                    keeper.cancel()
        except Exception as exc:
            self.failed_at = time.monotonic()
            log.warning(
                "live_stt_session_failed",
                recording_id=self.recording_id,
                error=type(exc).__name__,
            )
        finally:
            self.active = False
            log.info("live_stt_session_closed", recording_id=self.recording_id,
                     lines=len(self.lines))

    async def _send_loop(self, ws) -> None:
        while True:
            item = await self.queue.get()
            if item is None:
                await ws.send(json.dumps({"type": "CloseStream"}))
                return
            await ws.send(item)

    async def _keepalive_loop(self, ws) -> None:
        # Deepgram drops streams that go silent; our chunks arrive ~10 s apart
        while True:
            await asyncio.sleep(KEEPALIVE_SECONDS)
            await ws.send(json.dumps({"type": "KeepAlive"}))

    def _handle_message(self, message) -> None:
        try:
            data = json.loads(message)
        except (TypeError, ValueError):
            return
        if data.get("type") != "Results" or not data.get("is_final"):
            return
        alternatives = (data.get("channel") or {}).get("alternatives") or []
        text = (alternatives[0].get("transcript") if alternatives else "").strip()
        if text:
            words = alternatives[0].get("words") or []
            speaker = words[0].get("speaker") if words else None
            self.lines.append({"t": data.get("start", 0.0), "text": text, "speaker": speaker})



class VoskSession(_BaseSession):
    """vosk-server's WebSocket protocol. It answers once per audio frame, so
    PCM is re-framed to ~250 ms — one 10 s frame would yield a single result
    and behave exactly like batch transcription."""

    wants_pcm = True
    FRAME_SECONDS = 0.25

    async def run(self) -> None:
        try:
            from websockets.asyncio.client import connect
        except ImportError:  # older websockets
            from websockets import connect  # type: ignore[no-redef]

        url = self.endpoint or "ws://localhost:2700"
        try:
            async with connect(url, ping_interval=20, ping_timeout=60) as ws:
                config = {"sample_rate": live_audio.SAMPLE_RATE, "words": True}
                if self.model:
                    # the model for this table's language. On a stock
                    # vosk-server this would swap the model for every connected
                    # client, so scripts/vosk-up.sh runs a patched asr_server.py
                    # that keeps the choice per-connection.
                    config["model"] = self.model
                await ws.send(json.dumps({"config": config}))
                log.info("live_stt_session_started", recording_id=self.recording_id, provider="vosk")
                while True:
                    item = await self.queue.get()
                    if item is None:
                        await ws.send(VOSK_EOF)
                        try:
                            self._handle_message(await asyncio.wait_for(ws.recv(), timeout=15))
                        except (TimeoutError, asyncio.CancelledError):
                            pass
                        return
                    for frame in live_audio.frames(item, self.FRAME_SECONDS):
                        await ws.send(frame)
                        self._handle_message(await ws.recv())
        except Exception as exc:
            self.failed_at = time.monotonic()
            log.warning(
                "live_stt_session_failed",
                recording_id=self.recording_id,
                provider="vosk",
                error=type(exc).__name__,
            )
        finally:
            self.active = False
            log.info("live_stt_session_closed", recording_id=self.recording_id,
                     lines=len(self.lines))

    def _handle_message(self, message) -> None:
        try:
            data = json.loads(message)
        except (TypeError, ValueError):
            return
        if "partial" in data:
            self.set_provisional(data["partial"])
            return
        words = data.get("result") or []
        self.add_line(data.get("text", ""), start=float(words[0]["start"]) if words else 0.0)


class MistralSession(_BaseSession):
    """Mistral Voxtral Realtime. The server speaks first (session.created),
    audio is base64 PCM inside JSON capped at 256 KiB per append, and partial
    text arrives as transcription.text.delta. No diarization in realtime."""

    wants_pcm = True
    APPEND_SECONDS = 4.0  # 128 KB, comfortably under the 256 KiB cap

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pending = ""

    async def run(self) -> None:
        try:
            from websockets.asyncio.client import connect
        except ImportError:  # older websockets
            from websockets import connect  # type: ignore[no-redef]

        model = self.model or "voxtral-mini-transcribe-realtime-2602"
        url = f"{self.endpoint or MISTRAL_URL}?model={urllib.parse.quote(model)}"
        try:
            async with connect(
                url,
                additional_headers={"Authorization": f"Bearer {self.api_key}"},
                ping_interval=20,
                ping_timeout=60,
            ) as ws:
                # the handshake is server-first: wait for session.created
                await asyncio.wait_for(ws.recv(), timeout=30)
                await ws.send(
                    json.dumps(
                        {
                            "type": "session.update",
                            "session": {
                                "audio_format": {
                                    "encoding": "pcm_s16le",
                                    "sample_rate": live_audio.SAMPLE_RATE,
                                },
                                "target_streaming_delay_ms": 1000,
                            },
                        }
                    )
                )
                log.info("live_stt_session_started", recording_id=self.recording_id,
                         provider="mistral")
                receiver = asyncio.create_task(self._receive_loop(ws))
                try:
                    while True:
                        item = await self.queue.get()
                        if item is None:
                            await ws.send(json.dumps({"type": "input_audio.flush"}))
                            await ws.send(json.dumps({"type": "input_audio.end"}))
                            await asyncio.sleep(2)
                            return
                        for frame in live_audio.frames(item, self.APPEND_SECONDS):
                            await ws.send(
                                json.dumps(
                                    {
                                        "type": "input_audio.append",
                                        "audio": base64.b64encode(frame).decode(),
                                    }
                                )
                            )
                finally:
                    receiver.cancel()
        except Exception as exc:
            self.failed_at = time.monotonic()
            log.warning(
                "live_stt_session_failed",
                recording_id=self.recording_id,
                provider="mistral",
                error=type(exc).__name__,
            )
        finally:
            self.active = False
            log.info("live_stt_session_closed", recording_id=self.recording_id,
                     lines=len(self.lines))

    async def _receive_loop(self, ws) -> None:
        async for message in ws:
            self._handle_message(message)

    def _handle_message(self, message) -> None:
        try:
            data = json.loads(message)
        except (TypeError, ValueError):
            return
        kind = data.get("type")
        if kind == "transcription.text.delta":
            self._pending += data.get("text") or ""
            self.set_provisional(self._pending)
        elif kind == "transcription.segment":
            # a segment supersedes the deltas accumulated for it
            self.add_line(
                data.get("text") or self._pending,
                start=float(data.get("start") or 0.0),
                speaker=data.get("speaker_id"),
            )
            self._pending = ""
        elif kind == "transcription.done":
            self.add_line(self._pending)
            self._pending = ""


class WhisperSession(_BaseSession):
    """Whisper endpoints have no single streaming protocol, so captions are
    produced from the ordinary transcription endpoint over a sliding window:
    each chunk transcribes the last WINDOW_SECONDS of audio and only the text
    past the previous window is committed. Cutting at fixed chunk boundaries
    would slice words in half, which is what makes naive per-chunk Whisper
    produce nonsense."""

    wants_pcm = True
    WINDOW_SECONDS = 20.0
    STEP_SECONDS = 10.0
    # Whisper invents fluent text over near-silence; drop those segments
    MAX_NO_SPEECH_PROB = 0.6

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._buffer = bytearray()
        self._consumed_seconds = 0.0
        # audio already dropped off the front of the rolling buffer, and how
        # much new audio has arrived since the last window was transcribed
        self._dropped_seconds = 0.0
        self._pending_bytes = 0
        self._last_start: float | None = None

    async def run(self) -> None:
        log.info("live_stt_session_started", recording_id=self.recording_id, provider="whisper")
        try:
            while True:
                item = await self.queue.get()
                if item is None:
                    await self._transcribe_window(final=True)
                    return
                self._buffer.extend(item)
                self._pending_bytes += len(item)
                # transcribe once per STEP of NEW audio, not on every block:
                # keying off total length would fire on every 0.25 s once the
                # buffer passed the threshold
                if self._pending_bytes >= live_audio.BYTES_PER_SECOND * self.STEP_SECONDS:
                    await self._transcribe_window()
        except Exception as exc:
            self.failed_at = time.monotonic()
            log.warning(
                "live_stt_session_failed",
                recording_id=self.recording_id,
                provider="whisper",
                error=type(exc).__name__,
            )
        finally:
            self.active = False
            log.info("live_stt_session_closed", recording_id=self.recording_id,
                     lines=len(self.lines))

    async def _transcribe_window(self, final: bool = False) -> None:
        self._pending_bytes = 0
        window_bytes = int(live_audio.BYTES_PER_SECOND * self.WINDOW_SECONDS)
        window = bytes(self._buffer[-window_bytes:])
        if len(window) < live_audio.BYTES_PER_SECOND:  # under a second of audio
            return
        window_start = self._dropped_seconds + (
            (len(self._buffer) - len(window)) / live_audio.BYTES_PER_SECOND
        )
        # keep only what the next window can use, so a long round never grows
        # this buffer without bound
        if len(self._buffer) > window_bytes:
            self._dropped_seconds += (len(self._buffer) - window_bytes) / live_audio.BYTES_PER_SECOND
            del self._buffer[:-window_bytes]
        try:
            raw = await asyncio.to_thread(
                _whisper_window_request,
                self.endpoint,
                self.api_key,
                self.model,
                self.language,
                live_audio.wav_bytes(window),
            )
        except Exception:
            log.warning("live_stt_window_failed", recording_id=self.recording_id, exc_info=True)
            return

        committed = self._consumed_seconds
        for segment in raw.get("segments") or []:
            start = window_start + float(segment.get("start", 0.0))
            end = window_start + float(segment.get("end", 0.0))
            if end <= committed:  # already shown from an earlier window
                continue
            if float(segment.get("no_speech_prob", 0.0)) > self.MAX_NO_SPEECH_PROB:
                continue
            # a later window re-transcribes the tail with more context, so the
            # same sentence comes back improved — revise it instead of
            # printing it twice
            if (
                self._last_start is not None
                and abs(start - self._last_start) < 1.0
                and self.lines
            ):
                self._drop_provisional()
                if self.lines:
                    self.lines.pop()
            self.add_line(segment.get("text", ""), start=start)
            self._last_start = start
            committed = max(committed, end)
        if not (raw.get("segments") or []) and raw.get("text") and final:
            self.add_line(raw["text"], start=window_start)
        self._consumed_seconds = committed


def _whisper_window_request(
    base_url: str, api_key: str, model: str, language: str, wav: bytes
) -> dict:
    """Blocking call, run in a worker thread: the batch adapter's endpoint with
    a WAV window instead of the whole recording."""
    import httpx

    from citizens.providers.transcription import whisper as whisper_provider

    data = {"model": model or whisper_provider.DEFAULT_MODEL, "response_format": "verbose_json"}
    if language:
        data["language"] = language
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    endpoint = (base_url or whisper_provider.BASE_URL).rstrip("/") + "/audio/transcriptions"
    response = httpx.post(
        endpoint,
        headers=headers,
        data=data,
        files={"file": ("window.wav", wav, "audio/wav")},
        timeout=httpx.Timeout(120, connect=15),
    )
    response.raise_for_status()
    return response.json()


SESSION_TYPES = {
    "deepgram": DeepgramSession,
    "vosk": VoskSession,
    "mistral": MistralSession,
    "whisper": WhisperSession,
}


class LiveCaptionManager:
    def __init__(self):
        self._sessions: dict[str, _BaseSession] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @staticmethod
    def _resolve_vosk_model(config: dict, language: str) -> str:
        """Model path for this language, matching provider_config.vosk_model_for
        but reading the snapshot rather than the config store."""
        models = config.get("vosk_models") or {}
        code = (language or "").strip().lower()
        return models.get(code) or models.get(code.split("-")[0], "")

    def feed(self, recording_id: str, data: bytes, config: dict, language: str) -> None:
        """Called from the (threadpool) chunk-upload path. Never raises."""
        try:
            if self._loop is None or not config.get("enabled"):
                return
            provider = config.get("provider")
            if provider not in SESSION_TYPES:
                return
            # hosted engines need a key; self-hosted ones need an endpoint
            if provider in ("deepgram", "mistral") and not config.get("api_key"):
                return
            if provider in ("vosk", "whisper") and not config.get("endpoint"):
                return
            asyncio.run_coroutine_threadsafe(
                self._feed_async(recording_id, data, config, language), self._loop
            )
        except Exception:
            log.warning("live_stt_feed_failed", recording_id=recording_id, exc_info=True)

    def finish(self, recording_id: str) -> None:
        try:
            if self._loop is not None:
                asyncio.run_coroutine_threadsafe(self._finish_async(recording_id), self._loop)
        except Exception:
            pass

    def status(self, recording_id: str) -> dict:
        session = self._sessions.get(recording_id)
        if session is None:
            return {"active": False, "lines": []}
        return {"active": session.active, "lines": list(session.lines)}

    async def _feed_async(self, recording_id: str, data: bytes, config: dict, language: str) -> None:
        self._garbage_collect()
        session = self._sessions.get(recording_id)
        if session is not None and session.failed_at is not None:
            if time.monotonic() - session.failed_at < FAILURE_COOLDOWN:
                return  # cooling down; don't reconnect-loop (brief §51)
            self._sessions.pop(recording_id, None)
            session = None
        if session is None:
            provider = config["provider"]
            session_type = SESSION_TYPES[provider]
            model = config.get("model", "")
            if provider == "vosk":
                # Vosk needs a model per language and one server can hold
                # several, so this table's language picks it. Resolved from the
                # cached snapshot — never an OCS call on the upload path.
                model = self._resolve_vosk_model(config, language) or model
            session = session_type(
                recording_id,
                config.get("api_key") or "",
                model,
                language,
                endpoint=config.get("endpoint", ""),
            )
            session.task = asyncio.get_running_loop().create_task(session.run())
            if session.wants_pcm:
                # the phone sends fragments of one WebM stream; these engines
                # want PCM, so one ffmpeg decodes the stream for the session
                stream = live_audio.PcmStream(recording_id)
                if not await stream.start():
                    session.failed_at = time.monotonic()
                    return
                session.pcm_stream = stream
                asyncio.get_running_loop().create_task(self._pump_pcm(session, stream))
            self._sessions[recording_id] = session
        session.last_fed = time.monotonic()
        if session.wants_pcm:
            if session.pcm_stream is not None:
                session.pcm_stream.feed(data)
            return
        try:
            session.queue.put_nowait(data)
        except asyncio.QueueFull:
            log.warning("live_stt_queue_full", recording_id=recording_id)

    async def _pump_pcm(self, session: "_BaseSession", stream) -> None:
        """Forward decoded PCM into the session queue until the stream ends."""
        try:
            while True:
                pcm = await stream.read()
                if pcm is None:
                    break
                # backpressure, not drop: this runs in a background task, so
                # waiting for a slow engine costs nothing, whereas dropping
                # here silently loses words from the captions. PcmStream has
                # its own bounded buffer as the real safety valve.
                await session.queue.put(pcm)
        except Exception:
            log.warning("live_stt_pcm_pump_failed", recording_id=session.recording_id,
                        exc_info=True)
        finally:
            try:
                session.queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    async def _finish_async(self, recording_id: str) -> None:
        session = self._sessions.get(recording_id)
        if session is None:
            return
        if session.pcm_stream is not None:
            # closing ffmpeg's stdin flushes the tail, then _pump_pcm ends the queue
            await session.pcm_stream.close()
            return
        try:
            session.queue.put_nowait(None)
        except asyncio.QueueFull:
            if session.task:
                session.task.cancel()

    def _garbage_collect(self) -> None:
        now = time.monotonic()
        for recording_id, session in list(self._sessions.items()):
            if now - session.last_fed > SESSION_IDLE_TIMEOUT:
                if session.task and not session.task.done():
                    session.task.cancel()
                if session.pcm_stream is not None:
                    asyncio.get_running_loop().create_task(session.pcm_stream.close())
                self._sessions.pop(recording_id, None)

    async def shutdown(self) -> None:
        for session in self._sessions.values():
            if session.task and not session.task.done():
                session.task.cancel()
            if session.pcm_stream is not None:
                await session.pcm_stream.close()
        self._sessions.clear()


LIVE_CAPTIONS = LiveCaptionManager()
