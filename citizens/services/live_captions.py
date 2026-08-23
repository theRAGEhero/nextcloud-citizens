"""Provisional live captions (brief §34, §51).

The phone's ~10 s chunks — already uploaded for safety — are forwarded into a
server-side Deepgram streaming session per recording, so live captions cost
the phone zero extra bandwidth or battery. Captions are PROVISIONAL; the
canonical transcript always comes from batch transcription of the complete
audio. Any failure here is low-severity by design: recording is never
affected, and a dead session backs off instead of reconnect-looping.

Mistral's Voxtral Realtime uses a different protocol and is not wired up yet;
with Mistral as the STT provider, live captions simply report unavailable.
"""

import asyncio
import json
import time
import urllib.parse
from collections import deque

from citizens.logging_setup import get_logger

log = get_logger(__name__)

SESSION_IDLE_TIMEOUT = 180.0
FAILURE_COOLDOWN = 60.0
KEEPALIVE_SECONDS = 5.0
MAX_LINES = 80


class _LiveSession:
    def __init__(self, recording_id: str, api_key: str, model: str, language: str):
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
        }
        if self.language:
            params["language"] = self.language
        url = "wss://api.deepgram.com/v1/listen?" + urllib.parse.urlencode(params)
        try:
            async with connect(
                url, additional_headers={"Authorization": f"Token {self.api_key}"}
            ) as ws:
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
            self.lines.append({"t": data.get("start", 0.0), "text": text})


class LiveCaptionManager:
    def __init__(self):
        self._sessions: dict[str, _LiveSession] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def feed(self, recording_id: str, data: bytes, config: dict, language: str) -> None:
        """Called from the (threadpool) chunk-upload path. Never raises."""
        try:
            if self._loop is None or not config.get("enabled") or not config.get("api_key"):
                return
            if config.get("provider") != "deepgram":
                return  # Voxtral Realtime not wired yet — captions unavailable
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
            session = _LiveSession(
                recording_id, config["api_key"], config.get("model", ""), language
            )
            session.task = asyncio.get_running_loop().create_task(session.run())
            self._sessions[recording_id] = session
        session.last_fed = time.monotonic()
        try:
            session.queue.put_nowait(data)
        except asyncio.QueueFull:
            log.warning("live_stt_queue_full", recording_id=recording_id)

    async def _finish_async(self, recording_id: str) -> None:
        session = self._sessions.get(recording_id)
        if session is not None:
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
                self._sessions.pop(recording_id, None)

    async def shutdown(self) -> None:
        for session in self._sessions.values():
            if session.task and not session.task.done():
                session.task.cancel()
        self._sessions.clear()


LIVE_CAPTIONS = LiveCaptionManager()
