import pytest
from pydantic import ValidationError

from citizens.domain.analysis_schemas import TableAnalysis
from citizens.providers.analysis.openai_compat import _extract_json
from citizens.services.analysis import coalesce_segments


class Seg:
    def __init__(self, id, speaker, start, end, text):
        self.id = id
        self.speaker_label = speaker
        self.start_seconds = start
        self.end_seconds = end
        self.text = text


def test_coalesce_merges_same_speaker_fragments():
    segments = [
        Seg("a", "SPEAKER_01", 0.0, 1.0, "So"),
        Seg("b", "SPEAKER_01", 1.2, 2.0, "my name is"),
        Seg("c", "SPEAKER_01", 2.3, 3.0, "Giancarlo,"),
        Seg("d", "SPEAKER_02", 3.4, 4.0, "Nice to meet you."),
        Seg("e", "SPEAKER_01", 10.0, 11.0, "Later remark."),  # big gap → new block
    ]
    blocks = coalesce_segments(segments)
    assert len(blocks) == 3
    assert blocks[0]["ids"] == ["a", "b", "c"]
    assert blocks[0]["text"] == "So my name is Giancarlo,"
    assert blocks[1]["speaker"] == "SPEAKER_02"
    assert blocks[2]["ids"] == ["e"]


def test_extract_json_handles_fences_and_prose():
    assert _extract_json('```json\n{"findings": []}\n```') == {"findings": []}
    assert _extract_json('Here you go: {"findings": []} hope that helps') == {"findings": []}
    with pytest.raises(ValueError):
        _extract_json("no json here")


def test_table_schema_requires_evidence():
    with pytest.raises(ValidationError):
        TableAnalysis.model_validate(
            {"findings": [{"type": "proposal", "title": "Better buses", "summary": "x" * 5,
                           "evidence_segment_ids": []}]}
        )
    valid = TableAnalysis.model_validate(
        {"findings": [{"type": "proposal", "title": "Better buses", "summary": "Extend service.",
                       "evidence_segment_ids": ["seg-1"]}]}
    )
    assert valid.findings[0].type == "proposal"


def test_table_schema_rejects_unknown_type():
    with pytest.raises(ValidationError):
        TableAnalysis.model_validate(
            {"findings": [{"type": "vibe", "title": "ttt", "summary": "sss",
                           "evidence_segment_ids": ["seg-1"]}]}
        )
