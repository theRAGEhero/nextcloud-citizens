from citizens.providers.transcription import deepgram, mistral
from citizens.providers.transcription.base import SpeakerLabeler

DEEPGRAM_RAW = {
    "results": {
        "channels": [
            {
                "alternatives": [
                    {
                        "transcript": "Hello there. General Kenobi.",
                        "words": [
                            {"word": "hello", "punctuated_word": "Hello",
                             "start": 0.1, "end": 0.4, "speaker": 0},
                            {"word": "there", "punctuated_word": "there.",
                             "start": 0.45, "end": 0.8, "speaker": 0},
                            {"word": "general", "punctuated_word": "General",
                             "start": 1.2, "end": 1.6, "speaker": 1},
                            {"word": "kenobi", "punctuated_word": "Kenobi.",
                             "start": 1.65, "end": 2.1, "speaker": 1},
                        ],
                    }
                ]
            }
        ],
        "utterances": [
            {
                "speaker": 0, "start": 0.1, "end": 0.8, "transcript": "Hello there.",
                "words": [
                    {"word": "hello", "punctuated_word": "Hello", "start": 0.1, "end": 0.4},
                    {"word": "there", "punctuated_word": "there.", "start": 0.45, "end": 0.8},
                ],
            },
            {
                "speaker": 1, "start": 1.2, "end": 2.1, "transcript": "General Kenobi.",
                "words": [
                    {"word": "general", "punctuated_word": "General", "start": 1.2, "end": 1.6},
                    {"word": "kenobi", "punctuated_word": "Kenobi.", "start": 1.65, "end": 2.1},
                ],
            },
            {"speaker": 0, "start": 2.5, "end": 2.9, "transcript": "Indeed."},
        ],
    }
}


def test_deepgram_normalization_utterances_and_speakers():
    result = deepgram.normalize(DEEPGRAM_RAW, model="nova-3", requested_language="en")
    assert result.provider == "deepgram"
    assert len(result.segments) == 3
    assert [s.speaker for s in result.segments] == ["SPEAKER_01", "SPEAKER_02", "SPEAKER_01"]
    assert result.segments[0].text == "Hello there."
    assert result.segments[0].words[1].text == "there."
    assert result.segments[1].start == 1.2
    assert result.language == "en"


def test_deepgram_normalization_no_utterances_fallback():
    raw = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "Just one line.",
                            "words": [
                                {"word": "just", "start": 0.0, "end": 0.2},
                                {"word": "line", "start": 0.5, "end": 0.9},
                            ],
                        }
                    ]
                }
            ]
        }
    }
    result = deepgram.normalize(raw, model="nova-3", requested_language="it")
    assert len(result.segments) == 1
    assert result.segments[0].speaker == ""
    assert result.segments[0].end == 0.9


def test_deepgram_normalization_silence():
    raw = {"results": {"channels": [{"alternatives": [{"transcript": "", "words": []}]}]}}
    result = deepgram.normalize(raw, model="nova-3", requested_language="en")
    assert result.segments == []


MISTRAL_RAW = {
    "model": "voxtral-mini-latest",
    "text": "Buongiorno a tutti. Grazie mille.",
    "language": "it",
    "segments": [
        {"text": "Buongiorno a tutti.", "start": 0.2, "end": 1.4, "speaker": "spk_0"},
        {"text": "Grazie mille.", "start": 2.0, "end": 2.8, "speaker": "spk_1"},
        {"text": "  ", "start": 3.0, "end": 3.1, "speaker": "spk_0"},
    ],
}


def test_mistral_normalization():
    result = mistral.normalize(MISTRAL_RAW, model="voxtral-mini-latest", requested_language="it")
    assert result.provider == "mistral"
    assert len(result.segments) == 2  # blank segment dropped
    assert [s.speaker for s in result.segments] == ["SPEAKER_01", "SPEAKER_02"]
    assert result.language == "it"


def test_mistral_normalization_text_only():
    raw = {"text": "Solo testo.", "segments": []}
    result = mistral.normalize(raw, model="m", requested_language="")
    assert len(result.segments) == 1
    assert result.segments[0].speaker == ""


def test_speaker_labeler_orders_by_first_appearance():
    labeler = SpeakerLabeler()
    assert labeler.label(7) == "SPEAKER_01"
    assert labeler.label(2) == "SPEAKER_02"
    assert labeler.label(7) == "SPEAKER_01"
    assert labeler.label(None) == ""
