# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live caption message parsing (speaker-grouped provisional captions)."""

import json

from citizens.services.live_captions import DeepgramSession


def make_session() -> DeepgramSession:
    return DeepgramSession("rec-1", "key", "nova-3", "en")


def message(text: str, speaker: int | None, start: float = 1.0) -> str:
    first_word = text.split()[0] if text.split() else ""
    words = [] if speaker is None else [{"word": first_word, "speaker": speaker}]
    return json.dumps(
        {
            "type": "Results",
            "is_final": True,
            "start": start,
            "channel": {"alternatives": [{"transcript": text, "words": words}]},
        }
    )


def test_final_results_carry_speaker():
    session = make_session()
    session._handle_message(message("Hello there.", speaker=0))
    session._handle_message(message("Nice to meet you.", speaker=1))
    assert list(session.lines) == [
        {"t": 1.0, "text": "Hello there.", "speaker": 0},
        {"t": 1.0, "text": "Nice to meet you.", "speaker": 1},
    ]


def test_missing_words_yield_null_speaker():
    session = make_session()
    session._handle_message(message("No word data.", speaker=None))
    assert session.lines[0]["speaker"] is None


def test_interim_and_empty_results_ignored():
    session = make_session()
    session._handle_message(json.dumps({"type": "Results", "is_final": False}))
    session._handle_message(message("", speaker=0))
    session._handle_message("not json")
    assert len(session.lines) == 0


# --------------------------------------------------------- other engines

def test_vosk_session_keeps_finals_and_ignores_partials():
    from citizens.services.live_captions import VoskSession

    session = VoskSession("rec", "", "", "en", endpoint="ws://vosk:2700")
    # partials are shown provisionally: a table talking without pause would
    # otherwise see nothing at all until they stop
    session._handle_message(json.dumps({"partial": "the last"}))
    assert [line["text"] for line in session.lines] == ["the last"]
    assert session.lines[-1]["provisional"] is True
    session._handle_message(json.dumps({"partial": "the last bus leaves"}))
    assert [line["text"] for line in session.lines] == ["the last bus leaves"]  # replaced

    session._handle_message(json.dumps({
        "text": "the last bus leaves too early",
        "result": [{"word": "the", "start": 1.5, "end": 1.7, "conf": 1.0}],
    }))
    # the final supersedes the provisional line rather than stacking on it
    assert [line["text"] for line in session.lines] == ["the last bus leaves too early"]
    assert "provisional" not in session.lines[-1]
    assert session.lines[0]["t"] == 1.5
    assert session.lines[0]["speaker"] is None  # Vosk does not diarize


def test_vosk_session_uses_the_byte_exact_eof():
    from citizens.services import live_captions

    # the server compares this with a literal string; json.dumps differs
    assert live_captions.VOSK_EOF == '{"eof" : 1}'


def test_mistral_session_accumulates_deltas_and_commits_segments():
    from citizens.services.live_captions import MistralSession

    session = MistralSession("rec", "key", "", "en")
    session._handle_message(json.dumps({"type": "session.created", "session": {}}))
    session._handle_message(json.dumps({"type": "transcription.text.delta", "text": "the last "}))
    session._handle_message(json.dumps({"type": "transcription.text.delta", "text": "bus"}))
    # deltas show as one growing provisional line
    assert [line["text"] for line in session.lines] == ["the last bus"]
    assert session.lines[-1]["provisional"] is True
    session._handle_message(json.dumps({
        "type": "transcription.segment",
        "text": "the last bus leaves too early",
        "start": 2.0,
        "end": 6.0,
    }))
    assert [line["text"] for line in session.lines] == ["the last bus leaves too early"]
    assert session.lines[0]["t"] == 2.0
    assert "provisional" not in session.lines[-1]


def test_mistral_session_flushes_pending_text_on_done():
    from citizens.services.live_captions import MistralSession

    session = MistralSession("rec", "key", "", "en")
    session._handle_message(json.dumps({"type": "transcription.text.delta", "text": "hello there"}))
    session._handle_message(json.dumps({"type": "transcription.done", "text": "hello there"}))
    assert [line["text"] for line in session.lines] == ["hello there"]


def test_mistral_appends_match_the_documented_chunk_duration():
    from citizens.services import live_audio
    from citizens.services.live_captions import MistralSession

    # Mistral's streaming example uses chunk_duration_ms=480
    assert MistralSession.APPEND_SECONDS == 0.48
    framer = live_audio.Framer(MistralSession.APPEND_SECONDS)
    pcm = b"\x00" * (live_audio.BYTES_PER_SECOND * 30)
    slices = framer.push(pcm) + framer.flush()
    assert {len(chunk) for chunk in slices[:-1]} == {framer.size}
    assert sum(len(chunk) for chunk in slices) == len(pcm)


def test_framer_never_splits_a_sample_and_loses_nothing():
    from citizens.services import live_audio

    framer = live_audio.Framer(0.2)
    pcm = b"\x01\x02" * 8000
    chunks = framer.push(pcm) + framer.flush()
    assert all(len(chunk) % 2 == 0 for chunk in chunks)
    assert b"".join(chunks) == pcm


def test_framer_carries_the_remainder_across_reads():
    """The regression that made live captions disagree with the transcript.

    ffmpeg is read in READ_SIZE blocks, which is not a whole number of frames.
    Framing each block on its own emitted a full frame then a short one — 8000
    bytes then 192, over and over — instead of a uniform stream.
    """
    from citizens.services import live_audio

    framer = live_audio.Framer(0.2)
    emitted = []
    for _ in range(20):
        emitted += framer.push(b"\x00" * live_audio.READ_SIZE)

    assert {len(frame) for frame in emitted} == {framer.size}, (
        "frames must be uniform while the stream is running"
    )
    tail = framer.flush()
    assert len(b"".join(emitted + tail)) == 20 * live_audio.READ_SIZE


def test_live_framing_matches_the_batch_provider_exactly():
    """What makes captions and the archived transcript the same text.

    Vosk is deterministic: identical model, identical audio and an identical
    frame sequence give an identical transcript. The live path only satisfies
    that last condition if its frames come out the way vosk.py slices a file.
    """
    from citizens.providers.transcription import vosk as vosk_provider
    from citizens.services import live_audio
    from citizens.services.live_captions import VoskSession

    assert live_audio.Framer(VoskSession.FRAME_SECONDS).size == vosk_provider.FRAME_BYTES

    pcm = bytes(range(256)) * 700  # 179,200 B — not a whole number of frames
    batch = [
        pcm[offset : offset + vosk_provider.FRAME_BYTES]
        for offset in range(0, len(pcm), vosk_provider.FRAME_BYTES)
    ]
    framer = live_audio.Framer(VoskSession.FRAME_SECONDS)
    live = []
    for offset in range(0, len(pcm), live_audio.READ_SIZE):
        live += framer.push(pcm[offset : offset + live_audio.READ_SIZE])
    live += framer.flush()
    assert live == batch


def test_whisper_session_commits_only_new_text_and_drops_hallucinations():
    import asyncio

    from citizens.services import live_audio
    from citizens.services.live_captions import WhisperSession

    session = WhisperSession("rec", "", "whisper-1", "en", endpoint="http://whisper/v1")
    session._buffer.extend(b"\x00" * (live_audio.BYTES_PER_SECOND * 20))

    responses = [
        {"segments": [
            {"start": 0.0, "end": 5.0, "text": "the last bus leaves too early",
             "no_speech_prob": 0.02},
            # Whisper invents fluent text over silence — must be dropped
            {"start": 5.0, "end": 10.0, "text": "Thank you.", "no_speech_prob": 0.93},
        ]},
        {"segments": [
            # already shown by the previous window
            {"start": 0.0, "end": 5.0, "text": "the last bus leaves too early",
             "no_speech_prob": 0.02},
            {"start": 10.0, "end": 14.0, "text": "we should extend the service",
             "no_speech_prob": 0.05},
        ]},
    ]

    def fake_request(*args, **kwargs):
        return responses.pop(0)

    import citizens.services.live_captions as module

    original = module._whisper_window_request
    module._whisper_window_request = fake_request
    try:
        asyncio.run(session._transcribe_window())
        asyncio.run(session._transcribe_window())
    finally:
        module._whisper_window_request = original

    texts = [line["text"] for line in session.lines]
    assert texts == ["the last bus leaves too early", "we should extend the service"]


def test_wav_wrapper_is_a_valid_riff_container():
    import io
    import wave

    from citizens.services import live_audio

    data = live_audio.wav_bytes(b"\x00\x00" * 1600)
    with wave.open(io.BytesIO(data)) as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == live_audio.SAMPLE_RATE
        assert handle.getsampwidth() == 2
