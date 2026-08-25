# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live caption message parsing (speaker-grouped provisional captions)."""

import json

from citizens.services.live_captions import _LiveSession


def make_session() -> _LiveSession:
    return _LiveSession("rec-1", "key", "nova-3", "en")


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
