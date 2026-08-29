# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turning a finished caption session into a transcript of record.

Only reached when an administrator has turned final transcription off, which
makes the captions the only account of what was said — so the conversion has to
be careful with what caption engines leave out, particularly end times.
"""

from citizens.services.transcription import transcript_from_live_captions


def _lines(*entries):
    return {"provider": "vosk", "model": "m", "language": "it", "lines": list(entries)}


def test_an_explicit_end_time_is_kept():
    result = transcript_from_live_captions(
        _lines({"t": 1.0, "end": 4.5, "text": "buongiorno"})
    )
    assert (result.segments[0].start, result.segments[0].end) == (1.0, 4.5)


def test_a_missing_end_runs_up_to_the_next_line():
    """Mistral often reports no end. Guessing a fixed length would overlap the
    next speaker or leave a false gap; the next line's start is what actually
    happened in the room."""
    result = transcript_from_live_captions(
        _lines({"t": 1.0, "text": "prima"}, {"t": 6.0, "text": "seconda"})
    )
    assert result.segments[0].end == 6.0
    # nothing follows the last line, so it gets a short tail rather than zero
    assert result.segments[1].end > result.segments[1].start


def test_a_nonsensical_end_is_repaired():
    result = transcript_from_live_captions(
        _lines({"t": 5.0, "end": 2.0, "text": "sbagliato"}, {"t": 9.0, "text": "dopo"})
    )
    assert result.segments[0].end == 9.0


def test_speakers_are_canonicalised_the_way_batch_providers_do():
    result = transcript_from_live_captions(
        _lines(
            {"t": 0.0, "text": "one", "speaker": 7},
            {"t": 1.0, "text": "two", "speaker": 3},
            {"t": 2.0, "text": "three", "speaker": 7},
        )
    )
    assert [s.speaker for s in result.segments] == ["SPEAKER_01", "SPEAKER_02", "SPEAKER_01"]


def test_no_speaker_means_no_label_not_a_made_up_one():
    result = transcript_from_live_captions(_lines({"t": 0.0, "text": "vosk has no speakers"}))
    assert result.segments[0].speaker == ""


def test_word_timings_survive_so_a_live_transcript_navigates_like_a_final_one():
    result = transcript_from_live_captions(
        _lines(
            {
                "t": 0.0,
                "end": 1.0,
                "text": "due parole",
                "words": [
                    {"text": "due", "start": 0.0, "end": 0.4},
                    {"text": "parole", "start": 0.5, "end": 1.0},
                ],
            }
        )
    )
    assert [w.text for w in result.segments[0].words] == ["due", "parole"]
    assert result.segments[0].words[1].end == 1.0


def test_blank_lines_are_dropped_rather_than_stored_as_empty_segments():
    result = transcript_from_live_captions(
        _lines({"t": 0.0, "text": "  "}, {"t": 1.0, "text": "reale"}, {"t": 2.0, "text": ""})
    )
    assert [s.text for s in result.segments] == ["reale"]


def test_captions_that_produced_nothing_convert_to_nothing():
    """The job turns this into TRANSCRIPTION_FAILED — an engine that never
    connected must not leave a table silently absent from the report."""
    assert transcript_from_live_captions(_lines()).segments == []
